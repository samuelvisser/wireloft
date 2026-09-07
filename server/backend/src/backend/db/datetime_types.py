from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


def utc_datetime(value: datetime, *, assume_naive_utc: bool = False) -> datetime:
    """Return an aware UTC datetime for one absolute instant.

    New values must be timezone-aware so WireLoft never guesses what a naive
    wall-clock time meant. The opt-in naive path exists only for values read
    from SQLite databases created before the UTC datetime contract, where
    WireLoft historically persisted UTC wall-clock values without an offset.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        if not assume_naive_utc:
            raise ValueError("Datetime values persisted by WireLoft must include a timezone")
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Persist absolute datetimes as UTC and always return aware UTC values.

    SQLite has no timezone-aware datetime storage. WireLoft therefore stores the
    UTC wall-clock representation there and restores UTC awareness when reading
    it back. Other SQLAlchemy dialects receive an aware UTC datetime directly.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        return dialect.type_descriptor(DateTime(timezone=dialect.name != "sqlite"))

    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        value = utc_datetime(value)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        return utc_datetime(value, assume_naive_utc=True)
