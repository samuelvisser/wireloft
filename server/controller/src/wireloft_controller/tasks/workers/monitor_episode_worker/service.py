from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Show, Episode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason
from dailywire_api.types.user_info import DwMembershipLevel
from ._helpers import get_show_from_params, get_progress_updater_ep, get_first_ep_with_status, save_status_metadata
from ...helpers.episodes.status import get_publish_status_from_dw


async def run_monitor_episode_worker(s: Session, *,
                                     episode_id: Optional[int] = None,
                                     episode_slug: Optional[str] = None,
                                     show_id: Optional[int] = None,
                                     show_slug: Optional[str] = None) -> None:
    print("Starting monitor_episode_worker")

    # Get show for the new episode
    show: Show | None = get_show_from_params(s, episode_id=episode_id, episode_slug=episode_slug, show_id=show_id, show_slug=show_slug)
    if show is None:
        raise ValueError("Show not found; provide a valid show_slug or resource_id")

    # Get the latest season
    if show.seasons is None or len(show.seasons) == 0:
        raise ValueError("Show has no seasons")
    latest_season = show.seasons[0]

    # Get latest 5 episodes from DW
    client = MiddlewareClient()
    latest_episodes, _, _ = client.get_episodes_paginated(show.slug, ByShowSeason(
        latest_season.slug,
        membership_plan=show.membership_level,
        page_size=5,
        order_by="CreatedAt_DESC"
    ))

    # Find the most relevant dw episode to use as a status updater (dw sometimes returns duplicate records for the same in-progress episode)
    dw_ep = get_progress_updater_ep(latest_episodes)
    dw_ep_detail = client.get_episode_details(dw_ep.slug, require_member_exclusive=show.membership_level != DwMembershipLevel.FREE.value)

    # First find the newest final episode
    latest_final_episode = get_first_ep_with_status(latest_episodes, EpisodePublishStatus.PUBLISHED_FINAL)

    # Find db record for the episode
    db_ep: Episode | None = (
        s.query(Episode)
        .filter(Episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value)
        .filter(Episode.index > latest_final_episode.index)
        .order_by(Episode.index.desc())
        .first()
    )
    if db_ep is None:
        # stop running this task
        return

    # Attach the new status to db record
    new_status = get_publish_status_from_dw(dw_ep, dw_ep_detail)
    db_ep.publish_status = new_status.value
    s.flush()

    # Save status-specific metadata
    save_status_metadata(s, episode=db_ep, status=new_status)