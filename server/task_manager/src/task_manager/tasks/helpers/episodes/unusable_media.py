from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from .quarantine import quarantine_episode_identifier


NO_USABLE_MEDIA_REASON_META_KEY = "no_usable_media.reason"
NO_USABLE_MEDIA_SINCE_META_KEY = "no_usable_media.since"


class NoUsableMediaReason(StrEnum):
    NOT_FOUND = "not_found"
    NO_SHOW_TODAY = "no_show_today"
    PROCESSING_TIMEOUT = "processing_timeout"
    MEDIA_UNUSABLE = "media_unusable"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _remove_tracking_keys(episode: Episode) -> None:
    keys = {NO_USABLE_MEDIA_REASON_META_KEY, NO_USABLE_MEDIA_SINCE_META_KEY}
    for item in list(episode.meta_items):
        if item.key in keys:
            episode.meta_items.remove(item)


def mark_episode_no_usable_media(
    s: Session,
    episode: Episode,
    *,
    reason: NoUsableMediaReason,
    now: datetime | None = None,
) -> None:
    """Enter/refresh NO_USABLE_MEDIA while preserving one continuous state clock."""
    current_since = episode_no_usable_media_since(episode)
    observed_at = current_since or _ensure_utc(now or datetime.now(timezone.utc))

    quarantine_episode_identifier(s, episode)

    # Update canonical metadata in place. Removing and re-adding the same keys in
    # one flush can make SQLAlchemy issue the INSERT before the orphan DELETE,
    # violating Metadata's (parent_table, parent_id, key) unique constraint.
    episode.set_meta(NO_USABLE_MEDIA_REASON_META_KEY, reason.value)
    episode.set_meta(NO_USABLE_MEDIA_SINCE_META_KEY, observed_at.isoformat())

    episode.publish_status = EpisodePublishStatus.NO_USABLE_MEDIA.value
    episode.metadata_is_final = False
    s.flush()


def clear_episode_no_usable_media_tracking(episode: Episode) -> None:
    """Forget only the incident reason/clock after a successful recovery."""
    _remove_tracking_keys(episode)


def episode_no_usable_media_reason(episode: Episode) -> NoUsableMediaReason | None:
    raw = episode.get_meta(NO_USABLE_MEDIA_REASON_META_KEY)
    if not raw:
        return None
    try:
        return NoUsableMediaReason(raw)
    except ValueError:
        return None


def episode_no_usable_media_since(episode: Episode) -> datetime | None:
    raw = episode.get_meta(NO_USABLE_MEDIA_SINCE_META_KEY)
    if not raw:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None
