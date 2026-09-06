from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus


NO_USABLE_MEDIA_REASON_META_KEY = "no_usable_media.reason"
NO_USABLE_MEDIA_SINCE_META_KEY = "no_usable_media.since"

# Development builds before NO_USABLE_MEDIA existed stored the same incident
# information under dw_processing.*. Read and clear those keys so existing rows
# move cleanly to the dedicated status without treating genuine DW processing as
# an unusable-media incident.
_LEGACY_REASON_META_KEY = "dw_processing.reason"
_LEGACY_SINCE_META_KEY = "dw_processing.since"


class NoUsableMediaReason(StrEnum):
    NOT_FOUND = "not_found"
    NO_SHOW_TODAY = "no_show_today"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _raw_reason(episode: Episode) -> str | None:
    return (
        episode.get_meta(NO_USABLE_MEDIA_REASON_META_KEY)
        or episode.get_meta(_LEGACY_REASON_META_KEY)
    )


def _raw_since(episode: Episode) -> str | None:
    return (
        episode.get_meta(NO_USABLE_MEDIA_SINCE_META_KEY)
        or episode.get_meta(_LEGACY_SINCE_META_KEY)
    )


def _remove_tracking_keys(episode: Episode) -> None:
    keys = {
        NO_USABLE_MEDIA_REASON_META_KEY,
        NO_USABLE_MEDIA_SINCE_META_KEY,
        _LEGACY_REASON_META_KEY,
        _LEGACY_SINCE_META_KEY,
    }
    for item in list(episode.meta_items):
        if item.key in keys:
            episode.meta_items.remove(item)


def mark_episode_no_usable_media(
        episode: Episode,
        *,
        reason: NoUsableMediaReason,
        now: datetime | None = None,
) -> None:
    """Move an episode into NO_USABLE_MEDIA and remember why/when.

    Repeated observations of the same reason preserve the original timestamp so
    cleanup can distinguish a transient 404 from an episode that has really been
    unavailable for hours. A different reason starts a fresh grace period.
    """
    current_reason = episode_no_usable_media_reason(episode)
    current_since = episode_no_usable_media_since(episode)
    observed_at = (
        current_since
        if current_reason is reason and current_since is not None
        else _ensure_utc(now or datetime.now(timezone.utc))
    )

    _remove_tracking_keys(episode)
    episode.set_meta(NO_USABLE_MEDIA_REASON_META_KEY, reason.value)
    episode.set_meta(NO_USABLE_MEDIA_SINCE_META_KEY, observed_at.isoformat())
    episode.publish_status = EpisodePublishStatus.NO_USABLE_MEDIA.value
    episode.metadata_is_final = False


def clear_episode_no_usable_media_tracking(episode: Episode) -> None:
    """Forget an unusable-media incident once Daily Wire exposes usable media."""
    _remove_tracking_keys(episode)


def episode_no_usable_media_reason(episode: Episode) -> NoUsableMediaReason | None:
    raw = _raw_reason(episode)
    if not raw:
        return None
    try:
        return NoUsableMediaReason(raw)
    except ValueError:
        return None


def episode_no_usable_media_since(episode: Episode) -> datetime | None:
    raw = _raw_since(episode)
    if not raw:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None
