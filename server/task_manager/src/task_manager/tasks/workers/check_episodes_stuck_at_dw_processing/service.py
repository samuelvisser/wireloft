from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_authorisation import DeviceAuthClient
from task_manager.events.transactional import queue_event
from ...helpers.episodes.events import episode_event_payload, queue_episode_status_events
from ...helpers.episodes.metadata import update_episode_from_dailywire
from ...helpers.episodes.no_show import is_no_show_today_title
from ...helpers.episodes.processing import (
    DwProcessingReason,
    clear_episode_dw_processing_tracking,
    episode_dw_processing_reason,
    episode_dw_processing_since,
    mark_episode_dw_processing,
)
from ...helpers.progress import update_progress
from ..monitor_episode_worker.scheduling import MONITOR_REQUESTED_EVENT


logger = logging.getLogger(__name__)
STUCK_DW_PROCESSING_DELETE_AFTER = timedelta(hours=4)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _episode_is_old_enough(episode: Episode, *, now: datetime) -> bool:
    reference = episode.published_date or episode.created_at
    if reference is None:
        return False
    return now - _ensure_utc(reference) >= STUCK_DW_PROCESSING_DELETE_AFTER


def _processing_incident_is_old_enough(episode: Episode, *, now: datetime) -> bool:
    since = episode_dw_processing_since(episode)
    if since is None:
        return False
    return now - since >= STUCK_DW_PROCESSING_DELETE_AFTER


def _delete_episode(s: Session, episode: Episode) -> None:
    queue_event(
        s,
        "episode.deleted",
        episode_event_payload(episode=episode, show=episode.show),
    )
    s.delete(episode)
    s.commit()


def _queue_monitor_recovery(s: Session, *, episode: Episode, show: Show, old_status: str) -> None:
    queue_event(
        s,
        MONITOR_REQUESTED_EVENT,
        episode_event_payload(episode=episode, show=show, old_status=old_status),
    )


async def run_check_episodes_stuck_at_dw_processing(
        s: Session,
        *,
        show_id: Optional[int] = None,
        show_slug: Optional[str] = None,
        progress=None,
) -> None:
    """Clean up Daily Wire placeholders/404 entries after a four-hour grace.

    Only two processing reasons are destructive: a known "No Show Today"
    placeholder or an episode whose detail endpoint has continuously returned 404.
    Generic Daily Wire processing remains owned by ``monitor_episode_worker`` and
    the normal publication-final timeout.
    """
    stmt = select(Episode).where(
        or_(
            Episode.publish_status == EpisodePublishStatus.DW_PROCESSING.value,
            # Legacy rows created before no-show placeholders were normalized to
            # DW_PROCESSING are included once so they can adopt the new state.
            Episode.is_no_show_today.is_(True),
        )
    )
    if show_id is not None:
        stmt = stmt.where(Episode.show_id == show_id)
    elif show_slug is not None:
        stmt = stmt.where(Episode.show.has(slug=show_slug))

    candidates = list(s.execute(stmt).scalars())
    if not candidates:
        update_progress(progress, 100, "No episodes stuck at dw_processing")
        print("check_episodes_stuck_at_dw_processing completed: nothing to check")
        return

    access_token: Optional[str] = None
    tokens = DeviceAuthClient().get_token()
    if tokens:
        access_token = tokens.access_token
    client = MiddlewareClient(access_token=access_token)

    now = datetime.now(timezone.utc)
    checked = 0
    removed = 0

    for episode in candidates:
        show: Show = episode.show
        old_status = episode.publish_status

        if episode.is_no_show_today:
            # Also migrates legacy placeholder rows into the generic non-usable
            # state. Repeated hourly checks preserve the original observed time.
            mark_episode_dw_processing(
                episode,
                reason=DwProcessingReason.NO_SHOW_TODAY,
                now=now,
            )
            if old_status != EpisodePublishStatus.DW_PROCESSING.value:
                queue_episode_status_events(
                    s,
                    episode=episode,
                    show=show,
                    old_status=old_status,
                    new_status=EpisodePublishStatus.DW_PROCESSING,
                    was_created=False,
                )
            s.commit()

        reason = episode_dw_processing_reason(episode)
        if reason not in {
            DwProcessingReason.NO_SHOW_TODAY,
            DwProcessingReason.NOT_FOUND,
        }:
            checked += 1
            update_progress(
                progress,
                int(checked / len(candidates) * 100),
                f"Checked {checked}/{len(candidates)} processing episode(s); removed {removed}",
            )
            continue

        # The cleanup condition means "this same unusable condition has persisted
        # for four hours", not merely "the episode happens to be old". Requiring
        # both clocks prevents a fresh 404 on an old episode from being deleted.
        if (
            not _episode_is_old_enough(episode, now=now)
            or not _processing_incident_is_old_enough(episode, now=now)
        ):
            checked += 1
            update_progress(
                progress,
                int(checked / len(candidates) * 100),
                f"Checked {checked}/{len(candidates)} processing episode(s); removed {removed}",
            )
            continue

        membership_plan = show.membership_level
        require_member_exclusive = membership_plan not in {
            WlDwMembershipLevel.FREE.value,
            WlDwMembershipLevel.WL_ANY.value,
        }
        if require_member_exclusive and access_token is None:
            logger.warning(
                "Cannot verify stuck episode %s without a valid token for membership level %s",
                episode.slug,
                membership_plan,
            )
            checked += 1
            update_progress(
                progress,
                int(checked / len(candidates) * 100),
                f"Checked {checked}/{len(candidates)} processing episode(s); removed {removed}",
            )
            continue

        try:
            detail = client.get_episode_details(
                episode.slug,
                require_member_exclusive=require_member_exclusive,
            )
        except MiddlewareAPIError as exc:
            if exc.status_code == 404:
                logger.info(
                    "Deleting episode %s after its unusable Daily Wire state persisted for four hours",
                    episode.slug,
                )
                _delete_episode(s, episode)
                removed += 1
            else:
                logger.warning(
                    "Could not verify stuck episode '%s': %s",
                    episode.slug,
                    exc,
                )
        else:
            if (
                reason is DwProcessingReason.NO_SHOW_TODAY
                and is_no_show_today_title(detail.title)
            ):
                # The placeholder itself still exists after four hours. It has no
                # playable content and no reason to remain in the local library.
                logger.info(
                    "Deleting No Show Today episode %s after four hours in dw_processing",
                    episode.slug,
                )
                _delete_episode(s, episode)
                removed += 1
            else:
                # Daily Wire recovered (or converted a placeholder into a real
                # episode). Persist fresh metadata, clear the destructive incident,
                # and make sure the high-frequency monitor owns lifecycle resolution
                # again. Scheduling by logical monitor id is idempotent.
                update_episode_from_dailywire(episode, detail)
                clear_episode_dw_processing_tracking(episode)
                episode.publish_status = EpisodePublishStatus.DW_PROCESSING.value
                episode.metadata_is_final = False
                s.flush()
                _queue_monitor_recovery(
                    s,
                    episode=episode,
                    show=show,
                    old_status=old_status,
                )
                s.commit()

        checked += 1
        update_progress(
            progress,
            int(checked / len(candidates) * 100),
            f"Checked {checked}/{len(candidates)} processing episode(s); removed {removed}",
        )

    message = f"Checked {checked} processing episode(s); removed {removed}"
    update_progress(progress, 100, message)
    print(f"check_episodes_stuck_at_dw_processing completed: {message}")
