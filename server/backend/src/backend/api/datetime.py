from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from backend.db.datetime_types import utc_datetime
from config import get_settings


def tz_datetime(value: datetime) -> datetime:
    """Return an instant in WireLoft's TZ timezone.

    Runtime values must already identify an absolute instant. Legacy naive SQLite
    values are made aware when they cross the database type boundary, so seeing a
    naive value here indicates a contract violation rather than legacy data.
    """
    utc_value = utc_datetime(value)
    return utc_value.astimezone(ZoneInfo(get_settings().timezone))


def api_datetime(value: datetime) -> str:
    """Serialize an instant with WireLoft's configured UTC offset."""
    return tz_datetime(value).isoformat()


def api_timezone_payload(value: Any) -> Any:
    """Recursively prepare non-ResponseBase API data for configured-TZ output.

    Most WireLoft response models inherit ``ResponseBase`` and therefore use
    ``api_datetime`` automatically. Daily Wire proxy records live in a separate
    package, so this converts their aware datetime values before FastAPI validates
    and serializes the declared response model.
    """
    if isinstance(value, datetime):
        return api_datetime(value)
    if isinstance(value, BaseModel):
        # This is an intermediate validation payload, not the final JSON output.
        # Serialization aliases are not necessarily valid input aliases (for
        # example, ``dw_id`` serializes as ``dwId`` but validates from ``id``), so
        # preserve Python field names until FastAPI applies the response model.
        return api_timezone_payload(value.model_dump(mode="python", by_alias=False))
    if isinstance(value, dict):
        return {key: api_timezone_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [api_timezone_payload(item) for item in value]
    return value
