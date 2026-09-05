from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_api.types.user_info import DwMembershipLevel
from task_manager.events.transactional import queue_event
from task_manager.scheduler.db import TaskOperation, TaskOperationTarget
from task_manager.scheduler.executor import trigger_now
from task_manager.scheduler.types import OperationStatus
from ...helpers.episodes.events import episode_event_payload, queue_episode_status_events
from ...helpers.episodes.identifier import reconcile_episode_identifier_from_dailywire
from ...helpers.episodes.metadata import (
    metadata_refresh_offsets_seconds,
    metadata_watch_expired,
    update_episode_from_dailywire,
)
from ...helpers.episodes.processing import (
    DwProcessingReason,
    clear_episode_dw_processing_tracking,
    mark_episode_dw_processing,
)
from ..monitor_episode_worker.scheduling import MONITOR_REQUESTED_EVENT
from .scheduling import remove_episode_metadata_jobs, schedule_remaining_metadata_checks


logger = logging.getLogger(__name__)
_TASK_KEY = "refresh_episode_metadata_worker"
_ACTIVE_OPERATION_STATUSES = (
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
)


async def run_refresh_episode_metadata_worker(
        s: Session,
        *,
        episode_id: int | None,
        refresh: bool = False,
        scheduled_offset_seconds: int | None = None,
) -> bool:
    """Refresh or schedule metadata reconciliation; return whether a refresh ran."""
    if episode_id is None:
        _queue_startup_recovery(s)
        return False

    episode = s.get(Episode, episode_id)
    if episode is None:
        logger.info("Skipping metadata refresh for deleted episode %s", episode_id)
        return False

    if episode.metadata_is_final:
        remove_episode_metadata_jobs(episode.id)
        return False

    if episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value:
        # Automatic metadata settling applies only after publication. A manually
        # requested refresh may still reconcile one non-final record explicitly.
        if refresh:
            _refresh_episode_from_dailywire(s, episode)
            episode.metadata_is_final = False
            s.commit()
            return True
        return False

    configured_offsets = metadata_refresh_offsets_seconds()
    if (
        refresh
        and scheduled_offset_seconds is not None
        and scheduled_offset_seconds not in configured_offsets
    ):
        refresh = False

    did_refresh = False
    if refresh:
        detail_available = _refresh_episode_from_dailywire(s, episode)
        did_refresh = True
        if (
            not detail_available
            or episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value
        ):
            # A 404 or newly recognized placeholder moved the row back to
            # DW_PROCESSING. Final-metadata jobs no longer apply; normal episode
            # monitoring (or the hourly no-show cleanup) owns it from here.
            episode.metadata_is_final = False
            s.commit()
            remove_episode_metadata_jobs(episode.id)
            return did_refresh

    now = datetime.now(timezone.utc)
    if refresh and metadata_watch_expired(episode.published_date, now=now):
        episode.metadata_is_final = True
        s.commit()
        remove_episode_metadata_jobs(episode.id)
        logger.info("Episode %s metadata is final", episode.id)
        return did_refresh

    pending_jobs = schedule_remaining_metadata_checks(
        episode_id=episode.id,
        published_date=episode.published_date,
        now=now,
    )

    if refresh:
        s.commit()

    if not pending_jobs and metadata_watch_expired(episode.published_date, now=now):
        trigger_now(
            def_key=_TASK_KEY,
            resource_type="episode",
            resource_id=episode.id,
            refresh=True,
        )

    return did_refresh


def _queue_startup_recovery(s: Session) -> None:
    """Immediately recover unfinished automatic metadata work after a restart."""
    episodes = list(
        s.scalars(
            select(Episode).where(Episode.metadata_is_final.is_(False))
        )
    )

    queued_count = 0
    for episode in episodes:
        if episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value:
            continue
        if _has_active_operation_target(s, episode.id):
            continue

        trigger_now(
            def_key=_TASK_KEY,
            resource_type="episode",
            resource_id=episode.id,
            refresh=True,
        )
        queued_count += 1

    if queued_count:
        logger.info(
            "Queued immediate metadata recovery for %s episode(s)",
            queued_count,
        )


def _has_active_operation_target(s: Session, episode_id: int) -> bool:
    return s.scalar(
        select(TaskOperationTarget.id)
        .join(TaskOperation, TaskOperation.id == TaskOperationTarget.operation_id)
        .where(
            TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
            TaskOperationTarget.task_key == _TASK_KEY,
            TaskOperationTarget.resource_type == "episode",
            TaskOperationTarget.resource_id == episode_id,
        )
        .limit(1)
    ) is not None


def _refresh_episode_from_dailywire(s: Session, episode: Episode) -> bool:
    """Refresh one episode; return whether Daily Wire returned a detail record."""
    show = episode.show
    client = MiddlewareClient()
    old_status = episode.publish_status

    try:
        dw_episode = client.get_episode_details(
            episode.slug,
            require_member_exclusive=(
                show.membership_level != DwMembershipLevel.FREE.value
            ),
        )
    except MiddlewareAPIError as exc:
        if exc.status_code != 404:
            raise

        new_status = EpisodePublishStatus.DW_PROCESSING
        mark_episode_dw_processing(
            episode,
            reason=DwProcessingReason.NOT_FOUND,
        )
        queue_episode_status_events(
            s,
            episode=episode,
            show=show,
            old_status=old_status,
            new_status=new_status,
            was_created=False,
        )
        if not episode.is_no_show_today:
            queue_event(
                s,
                MONITOR_REQUESTED_EVENT,
                episode_event_payload(episode=episode, show=show, old_status=old_status),
            )
        s.flush()
        logger.info(
            "Daily Wire returned 404 while refreshing episode %s; status %s -> %s",
            episode.id,
            old_status,
            new_status.value,
        )
        return False

    update_episode_from_dailywire(episode, dw_episode)

    if episode.is_no_show_today:
        new_status = EpisodePublishStatus.DW_PROCESSING
        mark_episode_dw_processing(
            episode,
            reason=DwProcessingReason.NO_SHOW_TODAY,
        )
        queue_episode_status_events(
            s,
            episode=episode,
            show=show,
            old_status=old_status,
            new_status=new_status,
            was_created=False,
        )
    else:
        # A successful detail lookup ended any prior 404 incident. Metadata refresh
        # is also the reconciliation point for Daily Wire correcting episodeNumber
        # after initial indexing, regardless of the row's current lifecycle state.
        clear_episode_dw_processing_tracking(episode)
        reconcile_episode_identifier_from_dailywire(s, episode, dw_episode)

    s.flush()
    logger.info("Refreshed Daily Wire metadata for episode %s", episode.id)
    return True
