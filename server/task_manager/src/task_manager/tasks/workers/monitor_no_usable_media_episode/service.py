from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from config.network import NoInternetConnectionError, is_no_internet_error
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_authorisation import DeviceAuthClient
from task_manager.events.transactional import queue_event
from task_manager.scheduler.results import TaskResult
from ...helpers.episodes.events import episode_event_payload, queue_episode_status_events
from ...helpers.episodes.identifier_reconciliation import reconcile_episode_identifier
from ...helpers.episodes.metadata import METADATA_REFRESH_REQUESTED_EVENT, update_episode_from_dailywire
from ...helpers.episodes.no_show import is_no_show_today_slug
from ...helpers.episodes.quarantine import PREVIOUS_IDENTIFIER_META_KEY, restore_quarantined_identifier
from ...helpers.episodes.same_episode import PENDING_EPISODE_STATUSES
from ...helpers.episodes.status import observe_episode_detail, resolve_episode_status
from ...helpers.episodes.unusable_media import (
    NoUsableMediaReason,
    clear_episode_no_usable_media_tracking,
    episode_no_usable_media_since,
    mark_episode_no_usable_media,
)
from ...helpers.progress import update_progress
from ..monitor_pending_episode.scheduling import MONITOR_REQUESTED_EVENT


logger = logging.getLogger(__name__)
DEFAULT_NO_USABLE_MEDIA_DELETE_AFTER_MINUTES = 4 * 60


def _incident_expired(episode: Episode, *, now: datetime, minutes: int) -> bool:
    since = episode_no_usable_media_since(episode)
    return since is not None and now - since >= timedelta(minutes=max(0, minutes))


def _delete_episode(s: Session, episode: Episode) -> None:
    queue_event(s, "episode.deleted", episode_event_payload(episode=episode, show=episode.show))
    s.delete(episode)
    s.commit()


def _replacement_for_quarantined_episode(s: Session, episode: Episode) -> Episode | None:
    """Return a healthy row that reclaimed this quarantined row's canonical identifier."""
    previous_identifier = episode.get_meta(PREVIOUS_IDENTIFIER_META_KEY)
    if not previous_identifier:
        return None
    return s.scalar(
        select(Episode).where(
            Episode.show_id == episode.show_id,
            Episode.id != episode.id,
            Episode.episode_identifier == previous_identifier,
            Episode.publish_status != EpisodePublishStatus.NO_USABLE_MEDIA.value,
        ).limit(1)
    )


def _reason_for_unusable_detail(detail, observed_status: EpisodePublishStatus) -> NoUsableMediaReason:
    if is_no_show_today_slug(detail.slug):
        return NoUsableMediaReason.NO_SHOW_TODAY
    if observed_status is EpisodePublishStatus.DW_PROCESSING:
        return NoUsableMediaReason.PROCESSING_TIMEOUT
    return NoUsableMediaReason.MEDIA_UNUSABLE


def _membership(show: Show) -> bool:
    return show.membership_level not in {
        WlDwMembershipLevel.FREE.value,
        WlDwMembershipLevel.WL_ANY.value,
    }


def _recover_episode(s: Session, episode: Episode, detail) -> bool:
    """Recover a quarantined row only when settled media is currently usable."""
    # Quarantine recovery always applies the same media gate, including when
    # Daily Wire currently reports an otherwise-authoritative pending status.
    # The resulting snapshot is reused by the transition policy so HLS is never
    # fetched twice during one verification pass.
    observed = observe_episode_detail(detail, inspect_static_media=True)
    if is_no_show_today_slug(detail.slug) or not observed.has_usable_media:
        mark_episode_no_usable_media(
            s,
            episode,
            reason=_reason_for_unusable_detail(detail, observed.status),
        )
        return False

    # Resolve all remote/timer state before mutating the quarantined identifier so
    # transient HLS failures leave the row completely unchanged.
    resolved = resolve_episode_status(detail, snapshot=observed)
    if resolved.status is EpisodePublishStatus.NO_USABLE_MEDIA:
        mark_episode_no_usable_media(
            s,
            episode,
            reason=_reason_for_unusable_detail(detail, observed.status),
        )
        return False

    # Restoring the exact identifier displaced by quarantine is silent. Any
    # additional authoritative Daily Wire correction after that restoration is a
    # real identifier change and must use the normal downstream event path.
    if not restore_quarantined_identifier(s, episode):
        # A replacement already owns the canonical identifier. Preserve both Daily
        # Wire rows, but never expose duplicate logical media.
        mark_episode_no_usable_media(
            s,
            episode,
            reason=NoUsableMediaReason.MEDIA_UNUSABLE,
        )
        return False

    old_status = episode.publish_status
    update_episode_from_dailywire(episode, detail)
    reconcile_episode_identifier(s, episode, detail)
    clear_episode_no_usable_media_tracking(episode)
    episode.publish_status = resolved.status.value
    episode.metadata_is_final = False
    queue_episode_status_events(
        s,
        episode=episode,
        show=episode.show,
        old_status=old_status,
        new_status=resolved.status,
        was_created=False,
    )
    if resolved.status.value in PENDING_EPISODE_STATUSES:
        queue_event(
            s,
            MONITOR_REQUESTED_EVENT,
            episode_event_payload(episode=episode, show=episode.show, old_status=old_status),
        )
    elif resolved.status is EpisodePublishStatus.PUBLISHED_FINAL:
        queue_event(
            s,
            METADATA_REFRESH_REQUESTED_EVENT,
            episode_event_payload(episode=episode, show=episode.show, old_status=old_status),
        )
    s.commit()
    return True


def _target_result(
    *,
    episode_id: int,
    outcome: str,
    recovered_status: EpisodePublishStatus | None,
    episode_slug: str | None,
    verified: int,
    recovered: int,
    removed: int,
) -> TaskResult:
    """Return machine-readable facts for one targeted verification."""
    data: dict[str, str | int] = {
        "episode_id": episode_id,
        "outcome": outcome,
        "verified": verified,
        "recovered": recovered,
        "removed": removed,
    }
    if recovered_status is not None:
        data["publish_status"] = recovered_status.value
    if episode_slug:
        data["episode_slug"] = episode_slug

    return TaskResult(
        summary="No-usable-media episode verification completed",
        data=data,
    )


async def run_monitor_no_usable_media_episode(
    s: Session,
    *,
    show_id: Optional[int] = None,
    show_slug: Optional[str] = None,
    episode_id: Optional[int] = None,
    force: bool = False,
    delete_after_minutes: int = DEFAULT_NO_USABLE_MEDIA_DELETE_AFTER_MINUTES,
    progress=None,
) -> TaskResult:
    """Verify quarantined episodes, recover usable media, or delete confirmed 404s."""
    if force and episode_id is None:
        raise ValueError("Early Delete requires a specific episode_id")

    stmt = select(Episode).where(Episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value)
    if episode_id is not None:
        stmt = stmt.where(Episode.id == episode_id)
    elif show_id is not None:
        stmt = stmt.where(Episode.show_id == show_id)
    elif show_slug is not None:
        stmt = stmt.where(Episode.show.has(slug=show_slug))

    candidates = list(s.scalars(stmt))
    if not candidates:
        message = "No no-usable-media episodes to verify"
        update_progress(progress, 100, message)
        if episode_id is not None:
            return _target_result(
                episode_id=episode_id,
                outcome="already_resolved",
                recovered_status=None,
                episode_slug=None,
                verified=0,
                recovered=0,
                removed=0,
            )
        return TaskResult(
            summary=message,
            data={"verified": 0, "recovered": 0, "removed": 0},
        )

    tokens = DeviceAuthClient().get_token()
    access_token = tokens.access_token if tokens else None
    client = MiddlewareClient(access_token=access_token)
    now = datetime.now(timezone.utc)
    removed = recovered = verified = 0
    target_outcome: str | None = None
    target_recovered_status: EpisodePublishStatus | None = None
    target_slug: str | None = candidates[0].slug if episode_id is not None else None

    for index, episode in enumerate(candidates, start=1):
        is_target = episode_id == episode.id
        require_member_exclusive = _membership(episode.show)
        if require_member_exclusive and access_token is None:
            logger.warning("Cannot verify premium episode %s without a valid token", episode.slug)
            if is_target:
                target_outcome = "unverified"
            continue

        try:
            detail = client.get_episode_details(
                episode.slug,
                require_member_exclusive=require_member_exclusive,
            )
        except MiddlewareAPIError as exc:
            # Once the host itself is offline, trying every quarantined episode only
            # creates duplicate failures and keeps a DB-backed worker occupied longer.
            if is_no_internet_error(exc):
                s.rollback()
                raise NoInternetConnectionError() from exc
            if exc.status_code != 404:
                logger.warning("Could not verify no-usable-media episode %s: %s", episode.slug, exc)
                if is_target:
                    target_outcome = "unverified"
                continue
            verified += 1
            mark_episode_no_usable_media(
                s,
                episode,
                reason=NoUsableMediaReason.NOT_FOUND,
                now=now,
            )
            s.commit()
            if force or _incident_expired(episode, now=now, minutes=delete_after_minutes):
                replacement = _replacement_for_quarantined_episode(s, episode) if is_target else None
                replacement_status = (
                    EpisodePublishStatus(replacement.publish_status)
                    if replacement is not None
                    else None
                )
                replacement_slug = replacement.slug if replacement is not None else None
                logger.info("Deleting confirmed-404 episode %s", episode.slug)
                _delete_episode(s, episode)
                removed += 1
                if is_target:
                    target_outcome = "replaced" if replacement is not None else "deleted"
                    target_recovered_status = replacement_status
                    target_slug = replacement_slug
            elif is_target:
                target_outcome = "retained"
        else:
            verified += 1
            try:
                if _recover_episode(s, episode, detail):
                    recovered += 1
                    if is_target:
                        target_outcome = "recovered"
                        target_recovered_status = EpisodePublishStatus(episode.publish_status)
                        target_slug = episode.slug
                else:
                    s.commit()
                    if is_target:
                        target_outcome = "retained"
                        target_slug = episode.slug
            except Exception as exc:
                s.rollback()
                if is_no_internet_error(exc):
                    raise NoInternetConnectionError() from exc
                logger.exception(
                    "Could not verify media usability for episode %s; leaving it quarantined",
                    episode.slug,
                )
                if is_target:
                    target_outcome = "unverified"

        update_progress(
            progress,
            int(index / len(candidates) * 100),
            f"Verified {index}/{len(candidates)} no-usable-media episode(s); recovered {recovered}, removed {removed}",
        )

    message = (
        f"Verified {len(candidates)} no-usable-media episode(s); "
        f"recovered {recovered}, removed {removed}"
    )
    update_progress(progress, 100, message)

    if episode_id is not None:
        return _target_result(
            episode_id=episode_id,
            outcome=target_outcome or "already_resolved",
            recovered_status=target_recovered_status,
            episode_slug=target_slug,
            verified=verified,
            recovered=recovered,
            removed=removed,
        )

    return TaskResult(
        summary=message,
        data={"verified": verified, "recovered": recovered, "removed": removed},
    )
