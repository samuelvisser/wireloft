from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_api.records import DwEpisodeDetailRecord
from task_manager.events.transactional import queue_event
from task_manager.scheduler.db import TaskOperation, TaskOperationTarget
from task_manager.scheduler.executor import trigger_now
from task_manager.scheduler.types import OperationStatus
from ...helpers.episodes.events import episode_event_payload, queue_episode_status_events
from ...helpers.episodes.identifier_reconciliation import reconcile_episode_identifier
from ...helpers.episodes.metadata import (
    metadata_refresh_offsets_seconds,
    metadata_watch_expired,
    update_episode_from_dailywire,
)
from ...helpers.episodes.no_show import is_no_show_today_slug
from ...helpers.episodes.same_episode import PENDING_EPISODE_STATUSES
from ...helpers.episodes.status import observe_episode_detail, resolve_episode_status
from ...helpers.episodes.unusable_media import NoUsableMediaReason, mark_episode_no_usable_media
from ..monitor_pending_episode.scheduling import MONITOR_REQUESTED_EVENT
from .scheduling import remove_episode_metadata_jobs, schedule_remaining_metadata_checks


logger = logging.getLogger(__name__)
_TASK_KEY = "refresh_episode_metadata"
_ACTIVE_OPERATION_STATUSES = (OperationStatus.QUEUED.value, OperationStatus.RUNNING.value)


async def run_refresh_episode_metadata(
    s: Session,
    *,
    episode_id: int | None,
    refresh: bool = False,
    scheduled_offset_seconds: int | None = None,
) -> bool:
    if episode_id is None:
        _queue_startup_recovery(s)
        return False

    episode = s.get(Episode, episode_id)
    if episode is None:
        return False
    if episode.metadata_is_final:
        remove_episode_metadata_jobs(episode.id)
        return False
    if episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value:
        return False

    configured_offsets = metadata_refresh_offsets_seconds()
    if refresh and scheduled_offset_seconds is not None and scheduled_offset_seconds not in configured_offsets:
        refresh = False

    did_refresh = False
    if refresh:
        did_refresh = True
        episode_slug = episode.slug
        require_member_exclusive = episode.show.membership_level not in {
            WlDwMembershipLevel.FREE.value,
            WlDwMembershipLevel.WL_ANY.value,
        }

        # Before calling The Daily Wire API, release the db transaction so others can use it
        s.rollback()
        detail = _fetch_episode_from_dailywire(
            episode_slug=episode_slug,
            require_member_exclusive=require_member_exclusive,
        )

        # In case the episode changed during the API call, reload it here
        episode = s.get(Episode, episode_id)
        if episode is None:
            return False
        if episode.metadata_is_final:
            remove_episode_metadata_jobs(episode.id)
            return False
        if episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value:
            return False

        if not _refresh_episode_from_dailywire(s, episode, detail):
            episode.metadata_is_final = False
            s.commit()
            remove_episode_metadata_jobs(episode.id)
            return True

    now = datetime.now(timezone.utc)
    if refresh and metadata_watch_expired(episode.published_date, now=now):
        episode.metadata_is_final = True
        s.commit()
        remove_episode_metadata_jobs(episode.id)
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
    episodes = list(s.scalars(select(Episode).where(
        Episode.metadata_is_final.is_(False),
        Episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value,
    )))
    for episode in episodes:
        if _has_active_operation_target(s, episode.id):
            continue
        trigger_now(
            def_key=_TASK_KEY,
            resource_type="episode",
            resource_id=episode.id,
            refresh=True,
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


def _no_usable_reason(detail, observed_status: EpisodePublishStatus) -> NoUsableMediaReason:
    if is_no_show_today_slug(detail.slug):
        return NoUsableMediaReason.NO_SHOW_TODAY
    if observed_status is EpisodePublishStatus.DW_PROCESSING:
        return NoUsableMediaReason.PROCESSING_TIMEOUT
    return NoUsableMediaReason.MEDIA_UNUSABLE


def _fetch_episode_from_dailywire(
    *,
    episode_slug: str,
    require_member_exclusive: bool,
) -> DwEpisodeDetailRecord | None:
    """Fetch one Daily Wire snapshot without any database transaction open."""
    client = MiddlewareClient()
    try:
        return client.get_episode_details(
            episode_slug,
            require_member_exclusive=require_member_exclusive,
        )
    except MiddlewareAPIError as exc:
        if exc.status_code != 404:
            raise
        return None


def _refresh_episode_from_dailywire(
    s: Session,
    episode: Episode,
    detail: DwEpisodeDetailRecord | None,
) -> bool:
    """Apply one fetched snapshot; return False when lifecycle ownership transfers."""
    show = episode.show
    old_status = episode.publish_status
    if detail is None:
        new_status = EpisodePublishStatus.NO_USABLE_MEDIA
        mark_episode_no_usable_media(s, episode, reason=NoUsableMediaReason.NOT_FOUND)
        queue_episode_status_events(
            s,
            episode=episode,
            show=show,
            old_status=old_status,
            new_status=new_status,
            was_created=False,
        )
        s.flush()
        return False

    # Observe before mutating the row. A transient HLS/network failure therefore
    # raises and leaves the final episode untouched for normal task retry.
    observed = observe_episode_detail(detail)
    resolved = resolve_episode_status(
        detail,
        current_status=old_status,
        snapshot=observed,
    )
    new_status = resolved.status

    update_episode_from_dailywire(episode, detail)

    if new_status is EpisodePublishStatus.NO_USABLE_MEDIA:
        mark_episode_no_usable_media(
            s,
            episode,
            reason=_no_usable_reason(detail, observed.status),
        )
        queue_episode_status_events(
            s,
            episode=episode,
            show=show,
            old_status=old_status,
            new_status=new_status,
            was_created=False,
        )
        return False

    if new_status.value in PENDING_EPISODE_STATUSES:
        # Explicit scheduled/delayed/live evidence is authoritative even after a
        # row previously reached final. Transfer it back to pending monitoring.
        episode.publish_status = new_status.value
        episode.metadata_is_final = False
        queue_episode_status_events(
            s,
            episode=episode,
            show=show,
            old_status=old_status,
            new_status=new_status,
            was_created=False,
        )
        queue_event(
            s,
            MONITOR_REQUESTED_EVENT,
            episode_event_payload(episode=episode, show=show, old_status=old_status),
        )
        s.flush()
        return False

    # Final publication is sticky against weaker inferred countdown/processing
    # snapshots. Identifier corrections remain authoritative metadata changes.
    episode.publish_status = EpisodePublishStatus.PUBLISHED_FINAL.value
    reconcile_episode_identifier(
        s,
        episode,
        detail,
        previous_publish_status=old_status,
    )
    s.flush()
    return True
