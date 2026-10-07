from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from backend.db.datetime_types import utc_datetime
from backend.types.episode_types import (
    EpisodePublishStatus,
    PENDING_EPISODE_PUBLISH_STATUSES,
)


TRUSTED_LIVE_ENDED_META_KEY = "ep_status.trusted_live_ended"
TRUSTED_PUBLISHED_FINAL_META_KEY = "ep_status.trusted_published_final"
LAST_KNOWN_PENDING_META_KEY = "ep_status.last_known_pending"
RECORDED_PUBLISHED_FINAL_META_KEY = "ep_status.recorded_published_final"

_LIVE_ENDED_VALUE_PREFIX = "monitor:live_ended:"
_PUBLISHED_FINAL_VALUE_PREFIX = "monitor:published_final:"
_LAST_KNOWN_PENDING_VALUE_PREFIX = "wireloft:last_known_pending:"
_RECORDED_PUBLISHED_FINAL_VALUE_PREFIX = "wireloft:recorded_published_final:"


class EpisodePublicationTiming(Protocol):
    safe_live_ended: datetime | None
    safe_published_final: datetime | None
    last_known_pending: datetime | None
    recorded_published_final: datetime | None
    published_date: datetime | None

    def set_meta(self, key: str, value: str | None): ...


def encode_safe_live_ended(value: datetime) -> str:
    return f"{_LIVE_ENDED_VALUE_PREFIX}{utc_datetime(value).isoformat()}"


def encode_safe_published_final(value: datetime) -> str:
    return f"{_PUBLISHED_FINAL_VALUE_PREFIX}{utc_datetime(value).isoformat()}"


def encode_last_known_pending(value: datetime) -> str:
    return f"{_LAST_KNOWN_PENDING_VALUE_PREFIX}{utc_datetime(value).isoformat()}"


def encode_recorded_published_final(value: datetime) -> str:
    return f"{_RECORDED_PUBLISHED_FINAL_VALUE_PREFIX}{utc_datetime(value).isoformat()}"


def safe_live_ended_from_meta(value: str | None) -> datetime | None:
    return _timestamp_from_meta(value, prefix=_LIVE_ENDED_VALUE_PREFIX)


def safe_published_final_from_meta(value: str | None) -> datetime | None:
    return _timestamp_from_meta(value, prefix=_PUBLISHED_FINAL_VALUE_PREFIX)


def last_known_pending_from_meta(value: str | None) -> datetime | None:
    return _timestamp_from_meta(value, prefix=_LAST_KNOWN_PENDING_VALUE_PREFIX)


def recorded_published_final_from_meta(value: str | None) -> datetime | None:
    return _timestamp_from_meta(value, prefix=_RECORDED_PUBLISHED_FINAL_VALUE_PREFIX)


def invalidate_safe_publication_timing(
        episode: EpisodePublicationTiming,
        *,
        live_ended: bool = False,
        published_final: bool = False,
        observed_at: datetime | None = None,
) -> None:
    """Invalidate trusted monitor facts without discarding audit/lower-bound facts."""
    current = utc_datetime(observed_at or datetime.now(timezone.utc))
    marker = f"invalidated:{current.isoformat()}"
    if live_ended and episode.safe_live_ended is not None:
        episode.set_meta(TRUSTED_LIVE_ENDED_META_KEY, marker)
    if published_final and episode.safe_published_final is not None:
        episode.set_meta(TRUSTED_PUBLISHED_FINAL_META_KEY, marker)


def _invalidate_publication_lifecycle_timing(
        episode: EpisodePublicationTiming,
        *,
        live_ended: bool = False,
        published_final: bool = False,
        observed_at: datetime | None = None,
) -> None:
    """Invalidate WireLoft-derived timing facts when a new publication lifecycle starts."""
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


def _is_new_publication_lifecycle(
        *,
        old_status: str | None,
        new_status: EpisodePublishStatus,
) -> bool:
    """Return whether a status transition starts a new publication lifecycle."""
    if old_status == new_status.value:
        return False
    return (
        new_status in {
            EpisodePublishStatus.SCHEDULED,
            EpisodePublishStatus.DELAYED,
            EpisodePublishStatus.LIVE,
        }
        or (
            old_status == EpisodePublishStatus.PUBLISHED_FINAL.value
            and new_status in PENDING_EPISODE_PUBLISH_STATUSES
        )
    )


def record_publication_lifecycle_observation(
        episode: EpisodePublicationTiming,
        *,
        old_status: str | None,
        new_status: EpisodePublishStatus,
        observed_at: datetime | None = None,
) -> bool:
    """Update lifecycle timing facts and return whether a new lifecycle started."""
    current = utc_datetime(observed_at or datetime.now(timezone.utc))
    lifecycle_restarted = _is_new_publication_lifecycle(
        old_status=old_status,
        new_status=new_status,
    )
    if lifecycle_restarted:
        _invalidate_publication_lifecycle_timing(
            episode,
            live_ended=new_status in {
                EpisodePublishStatus.SCHEDULED,
                EpisodePublishStatus.DELAYED,
                EpisodePublishStatus.LIVE,
            },
            published_final=True,
            observed_at=current,
        )

    if new_status is EpisodePublishStatus.PUBLISHED_FINAL:
        record_published_final_observation(
            episode,
            observed_at=current,
        )
    return lifecycle_restarted


def record_published_final_observation(
        episode: EpisodePublicationTiming,
        *,
        observed_at: datetime | None = None,
) -> datetime:
    """Persist the first time WireLoft recorded PUBLISHED_FINAL this lifecycle."""
    existing = episode.recorded_published_final
    if existing is not None:
        return existing

    current = utc_datetime(observed_at or datetime.now(timezone.utc))
    episode.set_meta(
        RECORDED_PUBLISHED_FINAL_META_KEY,
        encode_recorded_published_final(current),
    )
    return current


def best_effort_published_date(episode: EpisodePublicationTiming) -> datetime | None:
    """Return WireLoft's best available publication timestamp for automation.

    A trusted continuously observed final transition wins. When a restart broke
    monitoring continuity, last_known_pending is only a lower bound; combine it
    with The Daily Wire's timestamp and use whichever is later. The first time
    WireLoft recorded PUBLISHED_FINAL is deliberately not used because it is an
    upper bound and may be hours late after downtime.
    """
    if episode.safe_published_final is not None:
        return utc_datetime(episode.safe_published_final)

    published_date = (
        utc_datetime(episode.published_date)
        if episode.published_date is not None
        else None
    )
    if episode.last_known_pending is None:
        return published_date

    last_known_pending = utc_datetime(episode.last_known_pending)
    if published_date is None:
        return last_known_pending
    return max(last_known_pending, published_date)


def _timestamp_from_meta(value: str | None, *, prefix: str) -> datetime | None:
    if not value or not value.startswith(prefix):
        return None
    raw_timestamp = value[len(prefix):]
    try:
        return utc_datetime(datetime.fromisoformat(raw_timestamp))
    except (TypeError, ValueError):
        return None
