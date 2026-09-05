from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_api.types.user_info import DwMembershipLevel
from task_manager.events.transactional import queue_event

from ._helpers import save_status_metadata
from .scheduling import MONITOR_COMPLETED_EVENT
from ...helpers.episodes.events import episode_event_payload, queue_episode_status_events
from ...helpers.episodes.metadata import metadata_watch_expired, update_episode_from_dailywire
from ...helpers.episodes.processing import (
    DwProcessingReason,
    clear_episode_dw_processing_tracking,
    mark_episode_dw_processing,
)
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
    """Refresh one already-indexed non-final episode until its lifecycle settles."""
    print(f"Starting monitor_episode_worker for {episode_slug or episode_id}")

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
    if db_episode is None:
        raise ValueError(
            "Monitored episode not found in database; "
            "fetch_new_episodes must index it before monitoring"
        )

    client = MiddlewareClient()
    try:
        dw_episode = client.get_episode_details(
            db_episode.slug,
            require_member_exclusive=(
                show.membership_level != DwMembershipLevel.FREE.value
            ),
        )
    except MiddlewareAPIError as exc:
        if exc.status_code != 404:
            raise

        # A list entry whose detail endpoint currently 404s is not usable media.
        # Keep it under the monitor lifecycle but put it in the generic processing
        # state. Repeated 404s preserve the first-observed timestamp, allowing the
        # hourly cleanup worker to remove entries that remain broken for four hours.
        old_status = db_episode.publish_status
        new_status = EpisodePublishStatus.DW_PROCESSING
        mark_episode_dw_processing(
            db_episode,
            reason=DwProcessingReason.NOT_FOUND,
        )
        s.flush()
        queue_episode_status_events(
            s,
            episode=db_episode,
            show=show,
            old_status=old_status,
            new_status=new_status,
            was_created=False,
        )
        s.commit()

        logger.info(
            "Daily Wire returned 404 for monitored episode %s; status %s -> %s",
            db_episode.slug,
            old_status,
            new_status.value,
        )
        print(
            f"monitor_episode_worker completed for {db_episode.slug}: "
            f"{new_status.value} (Daily Wire returned 404)"
        )
        return new_status

    new_status = get_publish_status_from_dw_detail(dw_episode)
    old_status = db_episode.publish_status

    update_episode_from_dailywire(db_episode, dw_episode)
    if new_status is EpisodePublishStatus.DW_PROCESSING:
        mark_episode_dw_processing(
            db_episode,
            reason=(
                DwProcessingReason.NO_SHOW_TODAY
                if db_episode.is_no_show_today
                else DwProcessingReason.DAILY_WIRE
            ),
        )
    else:
        db_episode.publish_status = new_status.value
        clear_episode_dw_processing_tracking(db_episode)
        if new_status is EpisodePublishStatus.PUBLISHED_FINAL:
            # This poll itself is a fresh metadata check. If the entire configured
            # settling window has already elapsed, no follow-up work is required.
            db_episode.metadata_is_final = metadata_watch_expired(db_episode.published_date)
        else:
            db_episode.metadata_is_final = False
    s.flush()

    save_status_metadata(
        s,
        episode=db_episode,
        dw_episode=dw_episode,
        status=new_status,
    )

    queue_episode_status_events(
        s,
        episode=db_episode,
        show=show,
        old_status=old_status,
        new_status=new_status,
        was_created=False,
    )

    if (
        new_status is EpisodePublishStatus.PUBLISHED_FINAL
        or db_episode.is_no_show_today
    ):
        # No-show placeholders are intentionally handed off to the hourly stuck
        # processing cleanup instead of being polled every monitor interval.
        queue_event(
            s,
            MONITOR_COMPLETED_EVENT,
            episode_event_payload(episode=db_episode, show=show, old_status=old_status),
        )

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
        episode_slug: str | None,
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

    if episode_slug is not None:
        episode = (
            s.query(Episode)
            .filter(Episode.show_id == show.id, Episode.slug == episode_slug)
            .one_or_none()
        )
        if episode is not None:
            return episode

    if episode_identifier is None:
        return None

    return (
        s.query(Episode)
        .filter(
            Episode.show_id == show.id,
            Episode.episode_identifier == episode_identifier,
        )
        .one_or_none()
    )
