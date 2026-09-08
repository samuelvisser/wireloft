from datetime import datetime, timezone, timedelta

from pydantic import AwareDatetime

from backend.db.datetime_types import utc_datetime


def date_is_min_ago(date, minutes: int) -> bool:
    if not date:
        return False
    instant = utc_datetime(date)
    now = datetime.now(timezone.utc)
    return (now - instant) >= timedelta(minutes=minutes)


def datetime_to_string(date: datetime | AwareDatetime) -> str:
    """Return the stable UTC representation used by date-based episode identifiers."""
    return utc_datetime(date).strftime("%Y-%m-%dT%H:%M:%S.%f")
