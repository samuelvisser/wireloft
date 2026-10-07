from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.db.datetime_types import utc_datetime
from backend.db.models import Episode
from backend.types.episode_types import (
    EpisodePublishStatus,
    PENDING_EPISODE_PUBLISH_STATUSES,
)
from backend.utils.episode_publication_timing import (
    LAST_KNOWN_PENDING_META_KEY,
    TRUSTED_LIVE_ENDED_META_KEY,
    TRUSTED_PUBLISHED_FINAL_META_KEY,
    encode_last_known_pending,
    encode_safe_live_ended,
    encode_safe_published_final,
    record_publication_lifecycle_observation,
)


MONITOR_LIVE_SESSION_META_KEY = "ep_status.monitor_live_session"
MONITOR_PENDING_SESSION_META_KEY = "ep_status.monitor_pending_session"

_MONITOR_SESSION_ID = uuid4().hex
_MONITORED_PENDING_STATUSES = PENDING_EPISODE_PUBLISH_STATUSES
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

    lifecycle_restarted = record_publication_lifecycle_observation(
        episode,
        old_status=old_status,
        new_status=new_status,
        observed_at=current,
    )
    if lifecycle_restarted:
        invalidated = f"invalidated:{current.isoformat()}"
        episode.set_meta(MONITOR_LIVE_SESSION_META_KEY, invalidated)
        episode.set_meta(MONITOR_PENDING_SESSION_META_KEY, invalidated)

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
