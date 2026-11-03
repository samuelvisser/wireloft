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
    from backend.db.models import Settings
    from task_manager.scheduler.db import (
        TaskDefinition,
        TaskOperation,
        TaskOperationDependency,
        TaskOperationRun,
        TaskOperationTarget,
        TaskRun,
        TaskSchedule,
    )

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
            Settings.__table__,
            TaskDefinition.__table__,
            TaskSchedule.__table__,
            TaskRun.__table__,
            TaskOperation.__table__,
            TaskOperationDependency.__table__,
            TaskOperationTarget.__table__,
            TaskOperationRun.__table__,
        ],
    )

    with session_factory() as session:
        session.add(Settings(onboarding_completed=True))
        session.commit()

    yield session_factory
    engine.dispose()

def available_artifact(path: Path | None = None) -> dict[str, object]:
    """Columns of a MediaDownload whose file is available.

    The database requires an available artifact to carry its filesystem identity:
    the identity of ``path``, or a placeholder for a test that never inspects the file.
    """
    if path is not None:
        from dailywire_downloader.storage.identity import inspect_artifact

        identity = inspect_artifact(path)
        return {
            "artifact_status": "available",
            "artifact_stat_dev": identity.stat_dev,
            "artifact_stat_ino": identity.stat_ino,
            "artifact_size_bytes": identity.size_bytes,
            "artifact_fingerprint": identity.fingerprint,
        }
    return {
        "artifact_status": "available",
        "artifact_stat_dev": "1",
        "artifact_stat_ino": "1",
        "artifact_size_bytes": 0,
        "artifact_fingerprint": "0" * 64,
    }


def mark_artifact_available(download, path: Path | None = None) -> None:
    for field, value in available_artifact(path).items():
        setattr(download, field, value)
