from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from backend.utils.episode_publication_timing import (
    TRUSTED_LIVE_ENDED_META_KEY,
    TRUSTED_PUBLISHED_FINAL_META_KEY,
    encode_safe_live_ended,
    encode_safe_published_final,
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
    return f"{_MONITOR_SESSION_ID}:{current.isoformat()}"


def _belongs_to_current_session(value: str | None) -> bool:
    return bool(value and value.startswith(f"{_MONITOR_SESSION_ID}:"))


def invalidate_safe_publication_timing(
        episode: Episode,
        *,
        live_ended: bool = False,
        published_final: bool = False,
        observed_at: datetime | None = None,
) -> None:
    """Invalidate safe facts that belong to an earlier publication lifecycle."""
    current = observed_at or datetime.now(timezone.utc)
    marker = f"invalidated:{current.isoformat()}"
    if live_ended and episode.safe_live_ended is not None:
        episode.set_meta(TRUSTED_LIVE_ENDED_META_KEY, marker)
    if published_final and episode.safe_published_final is not None:
        episode.set_meta(TRUSTED_PUBLISHED_FINAL_META_KEY, marker)


def track_monitor_publication_timing(
        episode: Episode,
        *,
        old_status: str | None,
        new_status: EpisodePublishStatus,
        observed_at: datetime | None = None,
) -> None:
    """Persist only publication timestamps the current monitor can prove.

    Saves episode metadata regarding its publication timing. As The Daily Wire-provided
    publication timestamp sometimes is not accurate to its actual publication, for
    WireLoft automations, this trusted timing might be used instead.

    safe_live_ended requires a LIVE -> LIVE observation before the episode
    leaves LIVE. This avoids treating first discovery of an already-live episode
    as proof that WireLoft observed the live phase continuously.

    safe_published_final requires any earlier pending-state observation in the
    same process. Therefore the first poll after a restart can never manufacture
    a fresh final-publication timestamp for an episode that may have finalized
    while WireLoft was offline.
    """
    current = observed_at or datetime.now(timezone.utc)

    if (
        new_status in {EpisodePublishStatus.SCHEDULED, EpisodePublishStatus.DELAYED}
        or (
            new_status is EpisodePublishStatus.LIVE
            and old_status != EpisodePublishStatus.LIVE.value
        )
    ):
        invalidate_safe_publication_timing(
            episode,
            live_ended=True,
            published_final=True,
            observed_at=current,
        )
    elif (
        old_status == EpisodePublishStatus.PUBLISHED_FINAL.value
        and new_status in _MONITORED_PENDING_STATUSES
    ):
        invalidate_safe_publication_timing(
            episode,
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
        if trusted_pending_session:
            episode.set_meta(
                TRUSTED_PUBLISHED_FINAL_META_KEY,
                encode_safe_published_final(current),
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
