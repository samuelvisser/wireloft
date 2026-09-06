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
from ...helpers.episodes.status import get_publish_status_from_dw_detail
from ...helpers.episodes.unusable_media import (
    NoUsableMediaReason,
    clear_episode_no_usable_media_tracking,
    episode_no_usable_media_reason,
    episode_no_usable_media_since,
    mark_episode_no_usable_media,
)
from ...helpers.progress import update_progress
from ..monitor_episode_worker.scheduling import MONITOR_REQUESTED_EVENT


logger = logging.getLogger(__name__)
DEFAULT_STUCK_WITHOUT_MEDIA_DELETE_AFTER_MINUTES = 4 * 60


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _episode_is_old_enough(
        episode: Episode,
        *,
        now: datetime,
        delete_after: timedelta,
) -> bool:
    reference = episode.published_date or episode.created_at
    if reference is None:
        return False
    return now - _ensure_utc(reference) >= delete_after


def _unusable_media_incident_is_old_enough(
        episode: Episode,
        *,
        now: datetime,
        delete_after: timedelta,
) -> bool:
    since = episode_no_usable_media_since(episode)
    if since is None:
        return False
    return now - since >= delete_after


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


async def run_cleanup_episodes_stuck_without_media(
        s: Session,
        *,
        show_id: Optional[int] = None,
        show_slug: Optional[str] = None,
        episode_id: Optional[int] = None,
        force: bool = False,
        delete_after_minutes: int = DEFAULT_STUCK_WITHOUT_MEDIA_DELETE_AFTER_MINUTES,
        progress=None,
) -> None:
    """Clean up known unusable-media incidents after the configured grace period.

    Scheduled cleanup only destroys two known NO_USABLE_MEDIA states: a
    "No Show Today" placeholder or an episode whose detail endpoint has
    continuously returned 404. A forced run is a deliberate UI override for one
    specific episode and removes that episode immediately while it is still in
    ``no_usable_media``.
    """
    if force and episode_id is None:
        raise ValueError("Forced cleanup requires a specific episode_id")

    delete_after = timedelta(minutes=max(0, delete_after_minutes))
    stmt = select(Episode).where(
        or_(
            Episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value,
            # Development builds before NO_USABLE_MEDIA existed stored 404/no-show
            # incidents under DW_PROCESSING. Include those rows once so the helper
            # can migrate recognized legacy incident metadata to the new status.
            Episode.publish_status == EpisodePublishStatus.DW_PROCESSING.value,
            Episode.is_no_show_today.is_(True),
        )
    )
    if episode_id is not None:
        stmt = stmt.where(Episode.id == episode_id)
    elif show_id is not None:
        stmt = stmt.where(Episode.show_id == show_id)
    elif show_slug is not None:
        stmt = stmt.where(Episode.show.has(slug=show_slug))

    candidates = list(s.execute(stmt).scalars())
    if not candidates:
        update_progress(progress, 100, "No episodes stuck without usable media")
        print("cleanup_episodes_stuck_without_media completed: nothing to check")
        return

    if force:
        episode = candidates[0]
        if episode.publish_status != EpisodePublishStatus.NO_USABLE_MEDIA.value:
            update_progress(progress, 100, "Episode no longer has no_usable_media status")
            print("cleanup_episodes_stuck_without_media completed: episode status changed")
            return

        logger.info("Early deleting no_usable_media episode %s", episode.slug)
        _delete_episode(s, episode)
        update_progress(progress, 100, "Deleted unusable-media episode early")
        print("cleanup_episodes_stuck_without_media completed: early deleted 1 episode")
        return

    access_token: Optional[str] = None
    client: MiddlewareClient | None = None

    now = datetime.now(timezone.utc)
    checked = 0
    removed = 0

    for episode in candidates:
        show: Show = episode.show
        old_status = episode.publish_status
        reason = episode_no_usable_media_reason(episode)

        if episode.is_no_show_today:
            mark_episode_no_usable_media(
                episode,
                reason=NoUsableMediaReason.NO_SHOW_TODAY,
                now=now,
            )
            reason = NoUsableMediaReason.NO_SHOW_TODAY
        elif (
            old_status == EpisodePublishStatus.DW_PROCESSING.value
            and reason in {
                NoUsableMediaReason.NO_SHOW_TODAY,
                NoUsableMediaReason.NOT_FOUND,
            }
        ):
            # Migrate legacy development rows that used DW_PROCESSING for the same
            # incident while preserving the original first-observed timestamp.
            mark_episode_no_usable_media(
                episode,
                reason=reason,
                now=now,
            )

        if (
            old_status != EpisodePublishStatus.NO_USABLE_MEDIA.value
            and episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value
        ):
            queue_episode_status_events(
                s,
                episode=episode,
                show=show,
                old_status=old_status,
                new_status=EpisodePublishStatus.NO_USABLE_MEDIA,
                was_created=False,
            )
            s.commit()

        reason = episode_no_usable_media_reason(episode)
        if (
            episode.publish_status != EpisodePublishStatus.NO_USABLE_MEDIA.value
            or reason not in {
                NoUsableMediaReason.NO_SHOW_TODAY,
                NoUsableMediaReason.NOT_FOUND,
            }
        ):
            checked += 1
            update_progress(
                progress,
                int(checked / len(candidates) * 100),
                f"Checked {checked}/{len(candidates)} unusable-media episode(s); removed {removed}",
            )
            continue

        # The cleanup condition means "this same unusable condition has persisted
        # for the configured grace period", not merely "the episode happens to be
        # old". Requiring both clocks prevents a fresh 404 on an old episode from
        # being deleted.
        if (
            not _episode_is_old_enough(
                episode,
                now=now,
                delete_after=delete_after,
            )
            or not _unusable_media_incident_is_old_enough(
                episode,
                now=now,
                delete_after=delete_after,
            )
        ):
            checked += 1
            update_progress(
                progress,
                int(checked / len(candidates) * 100),
                f"Checked {checked}/{len(candidates)} unusable-media episode(s); removed {removed}",
            )
            continue

        # Authentication and the Daily Wire client are intentionally lazy. Legacy
        # DW_PROCESSING rows are included above only so recognized pre-status-split
        # incidents can migrate; genuine processing rows should cause no remote work.
        if client is None:
            tokens = DeviceAuthClient().get_token()
            if tokens:
                access_token = tokens.access_token
            client = MiddlewareClient(access_token=access_token)

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
                f"Checked {checked}/{len(candidates)} unusable-media episode(s); removed {removed}",
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
                    "Deleting episode %s after its unusable Daily Wire state persisted for %s minutes",
                    episode.slug,
                    delete_after_minutes,
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
                reason is NoUsableMediaReason.NO_SHOW_TODAY
                and is_no_show_today_title(detail.title)
            ):
                logger.info(
                    "Deleting No Show Today episode %s after %s minutes with no usable media",
                    episode.slug,
                    delete_after_minutes,
                )
                _delete_episode(s, episode)
                removed += 1
            else:
                # Daily Wire recovered (or converted a placeholder into a real
                # episode). Persist fresh metadata and restore the lifecycle status
                # represented by the current detail response.
                update_episode_from_dailywire(episode, detail)
                clear_episode_no_usable_media_tracking(episode)
                recovered_status = get_publish_status_from_dw_detail(detail)
                episode.publish_status = recovered_status.value
                episode.metadata_is_final = False
                s.flush()
                queue_episode_status_events(
                    s,
                    episode=episode,
                    show=show,
                    old_status=old_status,
                    new_status=recovered_status,
                    was_created=False,
                )
                if recovered_status is not EpisodePublishStatus.PUBLISHED_FINAL:
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
            f"Checked {checked}/{len(candidates)} unusable-media episode(s); removed {removed}",
        )

    message = f"Checked {checked} unusable-media episode(s); removed {removed}"
    update_progress(progress, 100, message)
    print(f"cleanup_episodes_stuck_without_media completed: {message}")
