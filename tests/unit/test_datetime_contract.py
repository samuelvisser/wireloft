from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select
from sqlalchemy.exc import StatementError

from backend.api.models.base import ResponseBase
from backend.db.datetime_types import UTCDateTime
from task_manager.scheduler.db import TaskSchedule
from task_manager.scheduler import scheduler as scheduler_module


class _TimestampResponse(ResponseBase):
    occurred_at: datetime
    release_date: date


def test_sqlite_datetime_round_trip_is_utc() -> None:
    metadata = MetaData()
    records = Table(
        "datetime_contract_records",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("occurred_at", UTCDateTime(), nullable=False),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    source = datetime(2026, 9, 7, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    expected = datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc)

    with engine.begin() as connection:
        connection.execute(records.insert().values(id=1, occurred_at=source))
        stored = connection.exec_driver_sql(
            "SELECT occurred_at FROM datetime_contract_records WHERE id = 1"
        ).scalar_one()
        restored = connection.execute(
            select(records.c.occurred_at).where(records.c.id == 1)
        ).scalar_one()

    assert str(stored).startswith("2026-09-07 13:00:00")
    assert restored == expected
    assert restored.tzinfo is timezone.utc


def test_sqlite_datetime_rejects_new_naive_values() -> None:
    metadata = MetaData()
    records = Table(
        "datetime_contract_records",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("occurred_at", UTCDateTime(), nullable=False),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    with pytest.raises(StatementError, match="must include a timezone"):
        with engine.begin() as connection:
            connection.execute(
                records.insert().values(
                    id=1,
                    occurred_at=datetime(2026, 9, 7, 13, 0),
                )
            )


def test_api_datetime_uses_configured_timezone_and_keeps_dates(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.api.datetime.get_settings",
        lambda: SimpleNamespace(timezone="Europe/Amsterdam"),
    )

    response = _TimestampResponse(
        occurred_at=datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
        release_date=date(2026, 9, 7),
    )
    payload = json.loads(response.model_dump_json(by_alias=True))

    assert payload["occurredAt"] == "2026-09-07T15:00:00+02:00"
    assert payload["releaseDate"] == "2026-09-07"


def test_api_datetime_uses_dst_offset_from_configured_timezone(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.api.datetime.get_settings",
        lambda: SimpleNamespace(timezone="Europe/Amsterdam"),
    )

    response = _TimestampResponse(
        occurred_at=datetime(2026, 1, 7, 13, 0, tzinfo=timezone.utc),
        release_date=date(2026, 1, 7),
    )
    payload = json.loads(response.model_dump_json(by_alias=True))

    assert payload["occurredAt"] == "2026-01-07T14:00:00+01:00"


def test_scheduler_uses_application_timezone(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: SimpleNamespace(timezone="Europe/Amsterdam"),
    )

    cron_trigger = scheduler_module.get_trigger("cron", {"hour": 8})
    date_trigger = scheduler_module.get_trigger(
        "date",
        {"run_date": "2026-09-07T08:00:00", "timezone": "America/New_York"},
    )

    assert str(cron_trigger.timezone) == "Europe/Amsterdam"
    assert str(date_trigger.timezone) == "Europe/Amsterdam"
    assert date_trigger.run_date.utcoffset().total_seconds() == 2 * 60 * 60


def test_task_schedule_has_no_per_schedule_timezone() -> None:
    assert not hasattr(TaskSchedule, "timezone")
