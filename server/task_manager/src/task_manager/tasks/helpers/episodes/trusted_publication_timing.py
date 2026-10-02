from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus


TRUSTED_LIVE_ENDED_META_KEY = "ep_status.trusted_live_ended"
MONITOR_LIVE_SESSION_META_KEY = "ep_status.monitor_live_session"

_MONITOR_SESSION_ID = uuid4().hex
_POST_LIVE_STATUSES = frozenset({
    EpisodePublishStatus.DW_PROCESSING,
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
    EpisodePublishStatus.PUBLISHED_FINAL,
})
_TRUSTED_VALUE_PREFIX = "monitor:"


def is_trusted_automatic_download_delay_value(value: str | None) -> bool:
    return bool(value and value.startswith(_TRUSTED_VALUE_PREFIX))


def track_monitor_publication_timing(
        episode: Episode,
        *,
        old_status: str | None,
        new_status: EpisodePublishStatus,
        observed_at: datetime | None = None,
) -> None:
    """Track publication timing only when this monitor witnessed the live lifecycle.

    Saves episode metadata regarding its publication timing. As The Daily Wire-provided
    publication timestamp sometimes is not accurate to its actual publication, for
    WireLoft automations, this trusted timing might be used instead.

    If an episode was being monitored while it was live up until it was published,
    we can have a pretty good idea as to when we can safely assume it indeed was
    published. This function saves this timing if it can

    Trust begins only after the monitor observes LIVE while the persisted
    episode is already LIVE. That LIVE -> LIVE poll proves this process was
    actively following the episode during its live phase.

    A later LIVE -> processing/countdown/final transition in the same process is
    therefore accurate to roughly the pending-monitor interval and safely marks
    when the live stream ended. Without that LIVE -> LIVE proof, WireLoft
    falls back to The Daily Wire's publishedAt.
    """
    current = observed_at or datetime.now(timezone.utc)

    if (
        old_status == EpisodePublishStatus.LIVE.value
        and new_status is EpisodePublishStatus.LIVE
    ):
        episode.set_meta(
            MONITOR_LIVE_SESSION_META_KEY,
            f"{_MONITOR_SESSION_ID}:{current.isoformat()}",
        )
        return

    if old_status != EpisodePublishStatus.LIVE.value:
        return

    live_session = episode.get_meta(MONITOR_LIVE_SESSION_META_KEY)
    trusted_live_session = bool(
        live_session
        and live_session.startswith(f"{_MONITOR_SESSION_ID}:")
    )

    # Proof applies only to this one LIVE phase. Any exit consumes it, including
    # an unexpected regression/quarantine state where we deliberately decline to
    # establish a safer automatic-download clock.
    if trusted_live_session:
        episode.set_meta(
            MONITOR_LIVE_SESSION_META_KEY,
            f"consumed:{current.isoformat()}",
        )

    if not trusted_live_session or new_status not in _POST_LIVE_STATUSES:
        return

    episode.set_meta(
        TRUSTED_LIVE_ENDED_META_KEY,
        f"{_TRUSTED_VALUE_PREFIX}live_ended:{current.isoformat()}",
    )
