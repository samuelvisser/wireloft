from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.db.datetime_types import utc_datetime
from config import get_settings


def api_datetime(value: datetime) -> str:
    """Serialize an instant in WireLoft's configured wall-clock timezone.

    API consumers receive a normal ISO 8601 timestamp with an explicit UTC
    offset.
    """
    utc_value = utc_datetime(value, assume_naive_utc=True)
    configured_timezone = ZoneInfo(get_settings().timezone)
    return utc_value.astimezone(configured_timezone).isoformat()
