from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def clean_event_bus():
    from task_manager.events.registry import (
        WireloftEventLinker,
        shutdown_event_emitter,
        wait_for_events,
    )

    WireloftEventLinker.remove_all()
    yield
    wait_for_events()
    WireloftEventLinker.remove_all()
    shutdown_event_emitter()


@pytest.fixture
def task_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Configure scheduler tests with a file-backed, disposable SQLite DB."""
    from backend.db import core
    from backend.db.core import Base
    from task_manager.scheduler.db import TaskDefinition, TaskRun, TaskSchedule

    database_path = tmp_path / "wireloft-test.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    Base.metadata.create_all(
        engine,
        tables=[
            TaskDefinition.__table__,
            TaskSchedule.__table__,
            TaskRun.__table__,
        ],
    )

    yield session_factory
    engine.dispose()
