from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus


AUTOMATIC_DOWNLOAD_DELAY_META_KEY = "ep_status.automatic_download_delay"
MONITOR_LIVE_SESSION_META_KEY = "ep_status.monitor_live_session"

_MONITOR_SESSION_ID = uuid4().hex
_LIVE_ENTRY_STATUSES = frozenset({
    EpisodePublishStatus.SCHEDULED.value,
    EpisodePublishStatus.DELAYED.value,
})
_POST_LIVE_STATUSES = frozenset({
    EpisodePublishStatus.DW_PROCESSING,
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
    EpisodePublishStatus.PUBLISHED_FINAL,
})
_TRUSTED_DELAY_VALUE_PREFIX = "monitor:"


def is_trusted_automatic_download_delay_value(value: str | None) -> bool:
    return bool(value and value.startswith(_TRUSTED_DELAY_VALUE_PREFIX))


def track_monitor_publication_timing(
        episode: Episode,
        *,
        old_status: str | None,
        new_status: EpisodePublishStatus,
        observed_at: datetime | None = None,
) -> None:
    """Track publication timing only when this monitor witnessed the live lifecycle.

    A persisted LIVE row does not prove WireLoft was actually running when the
    episode went live; it may simply have survived a restart. The process-scoped
    session token deliberately loses that trust across restarts.

    Once this monitor session has witnessed SCHEDULED/DELAYED -> LIVE, the first
    LIVE -> processing/countdown/final transition in the same process is accurate
    to roughly the monitor interval and safely marks when the live stream ended.
    Otherwise Download Profiles fall back to The Daily Wire's publishedAt.
    """
    current = observed_at or datetime.now(timezone.utc)

    if (
        new_status is EpisodePublishStatus.LIVE
        and old_status in _LIVE_ENTRY_STATUSES
    ):
        episode.set_meta(
            MONITOR_LIVE_SESSION_META_KEY,
            f"{_MONITOR_SESSION_ID}:{current.isoformat()}",
        )
        return

    if (
        old_status != EpisodePublishStatus.LIVE.value
        or new_status is EpisodePublishStatus.LIVE
    ):
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
        AUTOMATIC_DOWNLOAD_DELAY_META_KEY,
        f"{_TRUSTED_DELAY_VALUE_PREFIX}live_ended:{current.isoformat()}",
    )
