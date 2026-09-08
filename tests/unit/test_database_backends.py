from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url


def test_database_url_overrides_sqlite_path_and_is_not_serialized():
    from config.settings.settings import AppSettings

    url = "postgresql+psycopg://wireloft:super-secret@db/wireloft"
    settings = AppSettings(database_url=url, database_path=Path("/ignored/wireloft.db"))

    assert settings.database_url == url
    assert settings.resolved_database_url == url
    assert "database_url" not in settings.model_dump()
    assert "super-secret" not in repr(settings)


def test_sqlite_path_only_exists_for_file_backed_sqlite():
    from backend.db import core

    assert core._sqlite_path(make_url("sqlite:////tmp/wireloft.db")) == Path("/tmp/wireloft.db")
    assert core._sqlite_path(make_url("sqlite:///:memory:")) is None
    assert core._sqlite_path(make_url("postgresql://user:secret@db/wireloft")) is None


def test_database_label_redacts_password(monkeypatch: pytest.MonkeyPatch):
    from backend.db import core

    fake_engine = SimpleNamespace(url=make_url("postgresql://wireloft:super-secret@db/wireloft"))
    monkeypatch.setattr(core, "_engine", fake_engine)

    label = core.get_database_label()

    assert "super-secret" not in label
    assert "***" in label
    assert label.startswith("postgresql://wireloft:")


def test_scheduler_enums_compile_as_varchar_on_postgresql():
    from task_manager.scheduler.db import TaskRun, TaskSchedule

    schedule_resource_type = TaskSchedule.__table__.c.resource_type.type
    run_resource_type = TaskRun.__table__.c.resource_type.type
    run_status = TaskRun.__table__.c.status.type

    assert schedule_resource_type.native_enum is False
    assert run_resource_type.native_enum is False
    assert run_status.native_enum is False
    assert str(schedule_resource_type.compile(dialect=postgresql.dialect())).startswith("VARCHAR")
    assert str(run_resource_type.compile(dialect=postgresql.dialect())).startswith("VARCHAR")
    assert str(run_status.compile(dialect=postgresql.dialect())).startswith("VARCHAR")


def test_cli_accepts_database_url_and_rejects_both_database_overrides():
    from backend.__main__ import _parse_args

    args = _parse_args([
        "db",
        "current",
        "--database-url",
        "postgresql+psycopg://wireloft@db/wireloft",
    ])
    assert args.database_url == "postgresql+psycopg://wireloft@db/wireloft"
    assert args.db is None

    with pytest.raises(SystemExit):
        _parse_args([
            "db",
            "current",
            "--db",
            "wireloft.db",
            "--database-url",
            "postgresql://db/wireloft",
        ])
