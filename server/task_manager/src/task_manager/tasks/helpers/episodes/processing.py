from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus


DW_PROCESSING_REASON_META_KEY = "dw_processing.reason"
DW_PROCESSING_SINCE_META_KEY = "dw_processing.since"


class DwProcessingReason(StrEnum):
    DAILY_WIRE = "dailywire"
    NOT_FOUND = "not_found"
    NO_SHOW_TODAY = "no_show_today"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def mark_episode_dw_processing(
        episode: Episode,
        *,
        reason: DwProcessingReason,
        now: datetime | None = None,
) -> None:
    """Move an episode into DW_PROCESSING and remember why/when it got stuck.

    Repeated observations of the same reason preserve the original timestamp so
    cleanup can distinguish one transient 404 from an episode that has really
    been unavailable for hours. A different reason starts a fresh grace period.
    """
    current_reason = episode.get_meta(DW_PROCESSING_REASON_META_KEY)
    current_since = episode.get_meta(DW_PROCESSING_SINCE_META_KEY)
    if current_reason != reason.value or not current_since:
        observed_at = _ensure_utc(now or datetime.now(timezone.utc))
        episode.set_meta(DW_PROCESSING_SINCE_META_KEY, observed_at.isoformat())
    episode.set_meta(DW_PROCESSING_REASON_META_KEY, reason.value)
    episode.publish_status = EpisodePublishStatus.DW_PROCESSING.value
    episode.metadata_is_final = False


def clear_episode_dw_processing_tracking(episode: Episode) -> None:
    """Forget a previous processing incident once Daily Wire becomes usable again."""
    for item in list(episode.meta_items):
        if item.key in {DW_PROCESSING_REASON_META_KEY, DW_PROCESSING_SINCE_META_KEY}:
            episode.meta_items.remove(item)


def episode_dw_processing_reason(episode: Episode) -> DwProcessingReason | None:
    raw = episode.get_meta(DW_PROCESSING_REASON_META_KEY)
    if not raw:
        return None
    try:
        return DwProcessingReason(raw)
    except ValueError:
        return None


def episode_dw_processing_since(episode: Episode) -> datetime | None:
    raw = episode.get_meta(DW_PROCESSING_SINCE_META_KEY)
    if not raw:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None
