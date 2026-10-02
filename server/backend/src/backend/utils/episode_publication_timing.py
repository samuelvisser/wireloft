from __future__ import annotations

from datetime import datetime

from backend.db.datetime_types import utc_datetime


TRUSTED_LIVE_ENDED_META_KEY = "ep_status.trusted_live_ended"
TRUSTED_PUBLISHED_FINAL_META_KEY = "ep_status.trusted_published_final"

_LIVE_ENDED_VALUE_PREFIX = "monitor:live_ended:"
_PUBLISHED_FINAL_VALUE_PREFIX = "monitor:published_final:"


def encode_safe_live_ended(value: datetime) -> str:
    return f"{_LIVE_ENDED_VALUE_PREFIX}{utc_datetime(value).isoformat()}"


def encode_safe_published_final(value: datetime) -> str:
    return f"{_PUBLISHED_FINAL_VALUE_PREFIX}{utc_datetime(value).isoformat()}"


def safe_live_ended_from_meta(value: str | None) -> datetime | None:
    return _safe_timestamp_from_meta(value, prefix=_LIVE_ENDED_VALUE_PREFIX)


def safe_published_final_from_meta(value: str | None) -> datetime | None:
    return _safe_timestamp_from_meta(value, prefix=_PUBLISHED_FINAL_VALUE_PREFIX)


def _safe_timestamp_from_meta(value: str | None, *, prefix: str) -> datetime | None:
    if not value or not value.startswith(prefix):
        return None
    raw_timestamp = value[len(prefix):]
    try:
        return utc_datetime(datetime.fromisoformat(raw_timestamp))
    except (TypeError, ValueError):
        return None
