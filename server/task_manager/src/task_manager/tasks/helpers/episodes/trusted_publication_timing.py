from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.db.datetime_types import utc_datetime
from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from backend.utils.episode_publication_timing import (
    LAST_KNOWN_PENDING_META_KEY,
    RECORDED_PUBLISHED_FINAL_META_KEY,
    TRUSTED_LIVE_ENDED_META_KEY,
    TRUSTED_PUBLISHED_FINAL_META_KEY,
    encode_last_known_pending,
    encode_safe_live_ended,
    encode_safe_published_final,
    record_published_final_observation,
)


MONITOR_LIVE_SESSION_META_KEY = "ep_status.monitor_live_session"
MONITOR_PENDING_SESSION_META_KEY = "ep_status.monitor_pending_session"

_MONITOR_SESSION_ID = uuid4().hex
_MONITORED_PENDING_STATUSES = frozenset({
    EpisodePublishStatus.SCHEDULED,
    EpisodePublishStatus.DELAYED,
    EpisodePublishStatus.LIVE,
    EpisodePublishStatus.DW_PROCESSING,
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
})
_POST_LIVE_STATUSES = frozenset({
    EpisodePublishStatus.DW_PROCESSING,
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
    EpisodePublishStatus.PUBLISHED_FINAL,
})


def _session_marker(current: datetime) -> str:
    return f"{_MONITOR_SESSION_ID}:{utc_datetime(current).isoformat()}"


def _belongs_to_current_session(value: str | None) -> bool:
    return bool(value and value.startswith(f"{_MONITOR_SESSION_ID}:"))


def _session_observed_at(value: str | None) -> datetime | None:
    """Read an unconsumed monitor-session marker from any process."""
    if not value:
        return None
    session_id, separator, raw_timestamp = value.partition(":")
    if not separator or session_id in {"consumed", "invalidated"}:
        return None
    try:
        return utc_datetime(datetime.fromisoformat(raw_timestamp))
    except (TypeError, ValueError):
        return None


def invalidate_safe_publication_timing(
        episode: Episode,
        *,
        live_ended: bool = False,
        published_final: bool = False,
        observed_at: datetime | None = None,
) -> None:
    """Invalidate only trusted monitor facts, preserving audit/lower-bound facts."""
    current = utc_datetime(observed_at or datetime.now(timezone.utc))
    marker = f"invalidated:{current.isoformat()}"
    if live_ended and episode.safe_live_ended is not None:
        episode.set_meta(TRUSTED_LIVE_ENDED_META_KEY, marker)
    if published_final and episode.safe_published_final is not None:
        episode.set_meta(TRUSTED_PUBLISHED_FINAL_META_KEY, marker)


def invalidate_publication_lifecycle_timing(
        episode: Episode,
        *,
        live_ended: bool = False,
        published_final: bool = False,
        observed_at: datetime | None = None,
) -> None:
    """Invalidate all timing facts when a genuinely new publication lifecycle starts."""
    current = utc_datetime(observed_at or datetime.now(timezone.utc))
    invalidate_safe_publication_timing(
        episode,
        live_ended=live_ended,
        published_final=published_final,
        observed_at=current,
    )
    if not published_final:
        return

    marker = f"invalidated:{current.isoformat()}"
    if episode.last_known_pending is not None:
        episode.set_meta(LAST_KNOWN_PENDING_META_KEY, marker)
    if episode.recorded_published_final is not None:
        episode.set_meta(RECORDED_PUBLISHED_FINAL_META_KEY, marker)


def is_new_publication_lifecycle(
        *,
        old_status: str | None,
        new_status: EpisodePublishStatus,
) -> bool:
    """Return whether a status transition starts a new publication lifecycle."""
    return (
        new_status in {EpisodePublishStatus.SCHEDULED, EpisodePublishStatus.DELAYED}
        or (
            new_status is EpisodePublishStatus.LIVE
            and old_status != EpisodePublishStatus.LIVE.value
        )
        or (
            old_status == EpisodePublishStatus.PUBLISHED_FINAL.value
            and new_status in _MONITORED_PENDING_STATUSES
        )
    )


def track_monitor_publication_timing(
        episode: Episode,
        *,
        old_status: str | None,
        new_status: EpisodePublishStatus,
        observed_at: datetime | None = None,
) -> None:
    """Persist publication facts that monitoring can prove or bound.

    safe_live_ended requires a LIVE -> LIVE observation before the episode leaves
    LIVE. safe_published_final requires an earlier pending-state observation in
    the same process.

    When a previous process observed a pending state but restarted before it could
    observe PUBLISHED_FINAL, that old observation is materialized as
    last_known_pending. It is only a lower bound, never promoted to a safe final
    timestamp. recorded_published_final stores the first time WireLoft observed
    the final state regardless of monitor continuity.
    """
    current = utc_datetime(observed_at or datetime.now(timezone.utc))

    if is_new_publication_lifecycle(
        old_status=old_status,
        new_status=new_status,
    ):
        invalidate_publication_lifecycle_timing(
            episode,
            live_ended=(
                new_status in {
                    EpisodePublishStatus.SCHEDULED,
                    EpisodePublishStatus.DELAYED,
                    EpisodePublishStatus.LIVE,
                }
            ),
            published_final=True,
            observed_at=current,
        )

    pending_session = episode.get_meta(MONITOR_PENDING_SESSION_META_KEY)
    trusted_pending_session = _belongs_to_current_session(pending_session)

    if (
        old_status == EpisodePublishStatus.LIVE.value
        and new_status is EpisodePublishStatus.LIVE
    ):
        episode.set_meta(
            MONITOR_LIVE_SESSION_META_KEY,
            _session_marker(current),
        )

    if (
        old_status == EpisodePublishStatus.LIVE.value
        and new_status is not EpisodePublishStatus.LIVE
    ):
        live_session = episode.get_meta(MONITOR_LIVE_SESSION_META_KEY)
        trusted_live_session = _belongs_to_current_session(live_session)
        if trusted_live_session:
            episode.set_meta(
                MONITOR_LIVE_SESSION_META_KEY,
                f"consumed:{current.isoformat()}",
            )
        if trusted_live_session and new_status in _POST_LIVE_STATUSES:
            episode.set_meta(
                TRUSTED_LIVE_ENDED_META_KEY,
                encode_safe_live_ended(current),
            )

    if (
        new_status is EpisodePublishStatus.PUBLISHED_FINAL
        and old_status != EpisodePublishStatus.PUBLISHED_FINAL.value
    ):
        record_published_final_observation(episode, observed_at=current)

        if trusted_pending_session:
            episode.set_meta(
                TRUSTED_PUBLISHED_FINAL_META_KEY,
                encode_safe_published_final(current),
            )
            episode.set_meta(
                MONITOR_PENDING_SESSION_META_KEY,
                f"consumed:{current.isoformat()}",
            )
        elif episode.safe_published_final is None:
            previous_pending_at = _session_observed_at(pending_session)
            if previous_pending_at is not None:
                episode.set_meta(
                    LAST_KNOWN_PENDING_META_KEY,
                    encode_last_known_pending(previous_pending_at),
                )
                episode.set_meta(
                    MONITOR_PENDING_SESSION_META_KEY,
                    f"consumed:{current.isoformat()}",
                )
        return

    if new_status in _MONITORED_PENDING_STATUSES:
        episode.set_meta(
            MONITOR_PENDING_SESSION_META_KEY,
            _session_marker(current),
        )
    elif trusted_pending_session:
        episode.set_meta(
            MONITOR_PENDING_SESSION_META_KEY,
            f"consumed:{current.isoformat()}",
        )
