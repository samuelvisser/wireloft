from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from backend.db.datetime_types import utc_datetime


TRUSTED_LIVE_ENDED_META_KEY = "ep_status.trusted_live_ended"
TRUSTED_PUBLISHED_FINAL_META_KEY = "ep_status.trusted_published_final"
LAST_KNOWN_PENDING_META_KEY = "ep_status.last_known_pending"
RECORDED_PUBLISHED_FINAL_META_KEY = "ep_status.recorded_published_final"

_LIVE_ENDED_VALUE_PREFIX = "monitor:live_ended:"
_PUBLISHED_FINAL_VALUE_PREFIX = "monitor:published_final:"
_LAST_KNOWN_PENDING_VALUE_PREFIX = "wireloft:last_known_pending:"
_RECORDED_PUBLISHED_FINAL_VALUE_PREFIX = "wireloft:recorded_published_final:"


class EpisodePublicationTiming(Protocol):
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
