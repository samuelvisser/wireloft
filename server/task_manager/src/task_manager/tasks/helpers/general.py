from datetime import datetime, timezone, timedelta

from pydantic import AwareDatetime


def date_is_min_ago(date, minutes: int) -> bool:
    if not date:
        return False
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    else:
        date = date.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - date) >= timedelta(minutes=minutes)


def datetime_to_string(date: datetime | AwareDatetime) -> str:
    return date.strftime("%Y-%m-%dT%H:%M:%S.%f")
