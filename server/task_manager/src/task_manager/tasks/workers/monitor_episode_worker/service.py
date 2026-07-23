from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Season, Show
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwEpisodeDetailRecord
from dailywire_api.types.user_info import DwMembershipLevel
from task_manager.events.transactional import queue_event

from ._helpers import save_status_metadata
from .scheduling import MONITOR_COMPLETED_EVENT
from ...helpers.episodes.save import upsert_episode
from ...helpers.episodes.status import get_publish_status_from_dw_detail
from ...helpers.shows.get import get_show_from_params


logger = logging.getLogger(__name__)


async def run_monitor_episode_worker(
        s: Session,
        *,
        episode_id: Optional[int] = None,
        episode_slug: Optional[str] = None,
        show_id: Optional[int] = None,
        show_slug: Optional[str] = None,
        season_id: Optional[int] = None,
        episode_identifier: Optional[str] = None,
        episode_index: Optional[int] = None,
) -> EpisodePublishStatus:
    """Refresh one exact non-final episode and persist its current state."""
    print(f"Starting monitor_episode_worker for {episode_slug or episode_id}")

    if episode_slug is None:
        raise ValueError("An episode slug is required to monitor an episode")

    show = get_show_from_params(
        s,
        episode_id=episode_id,
        episode_slug=episode_slug,
        show_id=show_id,
        show_slug=show_slug,
    )
    if show is None:
        raise ValueError("Show not found; provide a valid show_slug or show_id")

    db_episode = _find_episode(
        s,
        show=show,
        episode_id=episode_id,
        episode_slug=episode_slug,
        episode_identifier=episode_identifier,
    )
    season = _resolve_season(
        s,
        show=show,
        db_episode=db_episode,
        season_id=season_id,
    )

    client = MiddlewareClient()
    dw_episode = client.get_episode_details(
        episode_slug,
        require_member_exclusive=(
            show.membership_level != DwMembershipLevel.FREE.value
        ),
    )
    new_status = get_publish_status_from_dw_detail(dw_episode)

    was_created = db_episode is None
    old_status = db_episode.publish_status if db_episode is not None else None

    if db_episode is None:
        if episode_identifier is None or episode_index is None:
            raise ValueError(
                "A new monitored episode requires its identifier and local index"
            )
        db_episode = upsert_episode(
            s,
            show=show,
            season=season,
            ep=dw_episode.model_copy(
                update={"publish_status": new_status.value},
                deep=True,
            ),
            index_value=episode_index,
            ep_id=episode_identifier,
        )
    else:
        _update_episode_from_dailywire(db_episode, dw_episode)
        db_episode.publish_status = new_status.value
        s.flush()

    save_status_metadata(
        s,
        episode=db_episode,
        dw_episode=dw_episode,
        status=new_status,
    )

    event_data = {
        "resource_id": db_episode.id,
        "id": db_episode.id,
        "slug": db_episode.slug,
        "show_id": show.id,
        "show_slug": show.slug,
        "season_id": db_episode.season_id,
        "episode_identifier": db_episode.episode_identifier,
        "episode_index": db_episode.index,
        "old_status": old_status,
        "status": new_status.value,
    }

    if was_created:
        queue_event(s, "episode.added", event_data)

    if old_status != new_status.value:
        queue_event(s, "episode.status_updated", event_data)
        if new_status is EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN:
            queue_event(s, "episode.published_with_countdown", event_data)
        elif new_status is EpisodePublishStatus.PUBLISHED_FINAL:
            queue_event(s, "episode.published_final", event_data)

    if new_status is EpisodePublishStatus.PUBLISHED_FINAL:
        queue_event(s, MONITOR_COMPLETED_EVENT, event_data)

    s.commit()

    logger.info(
        "Episode %s status: %s -> %s",
        db_episode.slug,
        old_status,
        new_status.value,
    )
    print(
        f"monitor_episode_worker completed for {db_episode.slug}: "
        f"{new_status.value}"
    )
    return new_status


def _find_episode(
        s: Session,
        *,
        show: Show,
        episode_id: int | None,
        episode_slug: str,
        episode_identifier: str | None,
) -> Episode | None:
    if episode_id is not None:
        episode = (
            s.query(Episode)
            .filter(Episode.id == episode_id)
            .one_or_none()
        )
        if episode is not None:
            return episode

    episode = (
        s.query(Episode)
        .filter(Episode.show_id == show.id, Episode.slug == episode_slug)
        .one_or_none()
    )
    if episode is not None or episode_identifier is None:
        return episode

    return (
        s.query(Episode)
        .filter(
            Episode.show_id == show.id,
            Episode.episode_identifier == episode_identifier,
        )
        .one_or_none()
    )


def _resolve_season(
        s: Session,
        *,
        show: Show,
        db_episode: Episode | None,
        season_id: int | None,
) -> Season:
    if db_episode is not None:
        return db_episode.season
    if season_id is None:
        raise ValueError("A season id is required for a new monitored episode")

    season = s.get(Season, season_id)
    if season is None or season.show_id != show.id:
        raise ValueError(
            f"Season {season_id} does not belong to show '{show.slug}'"
        )
    return season


def _update_episode_from_dailywire(
        episode: Episode,
        dw_episode: DwEpisodeDetailRecord,
) -> None:
    """Update remote fields without changing Wireloft identity fields."""
    protected_fields = {
        "id",
        "show_id",
        "season_id",
        "index",
        "episode_identifier",
        "publish_status",
    }
    model_fields = set(Episode.__mapper__.attrs.keys())
    for field, value in dw_episode.model_dump(
            mode="python",
            by_alias=False,
    ).items():
        if field in model_fields and field not in protected_fields:
            setattr(episode, field, value)
