import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Show, Episode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient, ByShowSeason
from dailywire_api.records import DwEpisodeDetailRecord
from dailywire_api.types.user_info import DwMembershipLevel
from ._helpers import get_progress_updater_ep, get_first_ep_with_status, save_status_metadata
from ...helpers.episodes.status import get_publish_status_from_dw_detail
from ...helpers.shows.get import get_show_from_params


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
    else:
        print(f"Found show {show.slug} with id {show.id}")

    # Get the latest season
    if show.seasons is None or len(show.seasons) == 0:
        raise ValueError("Show has no seasons")
    latest_db_season = show.seasons[0]

    # Get latest 5 episodes from DW
    client = MiddlewareClient()
    latest_dw_episodes, _, _ = client.get_episodes_paginated(show.slug, ByShowSeason(
        season_dw_id=latest_db_season.dw_id,
        membership_plan=show.membership_level,
        page_size=5,
        order_by="CreatedAt_DESC"
    ))

    # Get details for all retrieved latest episodes
    latest_dw_detail_episodes: list[DwEpisodeDetailRecord] = list()
    for ep in latest_dw_episodes:
        dw_ep_detail = client.get_episode_details(ep.slug, require_member_exclusive=show.membership_level != DwMembershipLevel.FREE.value)
        latest_dw_detail_episodes.append(dw_ep_detail)

    # Find the most relevant dw episode to use as a status updater (dw sometimes returns duplicate records for the same in-progress episode)
    dw_ep = get_progress_updater_ep(latest_dw_detail_episodes)

    # Find the newest final episode that is not the progress updater
    latest_dw_final_ep = get_first_ep_with_status(latest_dw_detail_episodes, EpisodePublishStatus.PUBLISHED_FINAL, skip_ep=dw_ep)
    if latest_dw_final_ep is None:
        logging.error(f"No final episode found for show '{show.slug}'. This should never happen.")
        return

    print(f"Found monitoring episode {dw_ep.slug}")
    print(f"Found latest final episode {latest_dw_final_ep.slug}")


    status_test = get_publish_status_from_dw_detail(dw_ep)
    print(f"Found status: {status_test}")



    # Find db record for the episode
    latest_db_ep: Episode | None = (
        s.query(Episode)
        .filter(Episode.show_id == show.id)
        .order_by(Episode.index.desc())
        .first()
    )

    # Abort if no episodes found in db
    if latest_db_ep is None:
        message = f"No episodes found in the database for show '{show.slug}'. Aborting."
        logging.warning(f"Monitoring task aborting: {message}")
        print(message)
        return

    # If the newest db ep is not either the monitoring or latest final dw ep, the new episode finder should run first. Abort.
    if latest_db_ep.slug != dw_ep.slug and latest_db_ep.slug != latest_dw_final_ep.slug:
        logging.warning(f"Monitoring task aborting: did not find matching db episode for latest final dw ep: {latest_dw_final_ep.slug}. Aborting.")
        return

    # Create or update db record
    db_ep = latest_db_ep
    if db_ep.slug != dw_ep.slug:
        db_ep = Episode(
            show_id=show.id,
            dw_id=dw_ep.dw_id,
            index=dw_ep.index,
            title=dw_ep.title,
            slug=dw_ep.slug,
            duration=dw_ep.duration,
        )


    # Attach the new status to db record
    new_status = get_publish_status_from_dw_detail(dw_ep)
    db_ep.publish_status = new_status.value

    print(new_status)

    s.flush()

    # Save status-specific metadata
    save_status_metadata(s, episode=db_ep, status=new_status)
    # s.commit()