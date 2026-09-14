from __future__ import annotations

import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine


def test_database_instance_lock_rejects_second_process(tmp_path: Path) -> None:
    from backend.db.instance_lock import DatabaseInstanceLock

    database = tmp_path / "wireloft.db"
    database.touch()

    code = r"""
import sys
from backend.db.instance_lock import DatabaseInUseError, DatabaseInstanceLock

try:
    lock = DatabaseInstanceLock.acquire(sys.argv[1], command="second process")
except DatabaseInUseError as exc:
    assert "already owned by another WireLoft instance" in str(exc)
    assert "first process" in str(exc)
    raise SystemExit(0)
else:
    lock.release()
    raise SystemExit(3)
"""

    with DatabaseInstanceLock.acquire(database, command="first process"):
        result = subprocess.run(
            [sys.executable, "-c", code, str(database)],
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0, result.stderr or result.stdout


def test_database_instance_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    from backend.db.instance_lock import DatabaseInstanceLock

    database = tmp_path / "wireloft.db"
    database.touch()

    first = DatabaseInstanceLock.acquire(database, command="first")
    lock_path = first.lock_path
    first.release()

    # The stable lock-file inode intentionally remains. Kernel lock ownership,
    # not file existence, decides whether another WireLoft may use the database.
    assert lock_path.exists()
    with DatabaseInstanceLock.acquire(database, command="second") as second:
        assert second.lock_path == lock_path


def test_database_corruption_classifier_does_not_confuse_lock_contention() -> None:
    from backend.db.core import is_database_corruption_error

    assert is_database_corruption_error(
        sqlite3.DatabaseError("database disk image is malformed")
    )
    assert not is_database_corruption_error(RuntimeError("wrapped application bug"))
    assert not is_database_corruption_error(
        sqlite3.OperationalError("database is locked")
    )


def test_quick_check_rejects_malformed_database(tmp_path: Path, monkeypatch) -> None:
    from backend.db import core
    from backend.db.core import DatabaseCorruptionError

    database = tmp_path / "wireloft.db"
    database.write_bytes(b"this is not an sqlite database")
    engine = create_engine(f"sqlite:///{database.as_posix()}")

    monkeypatch.setattr(core, "_database_corruption_path", None)
    monkeypatch.setattr(core, "_database_corruption_message", None)
    try:
        with pytest.raises(DatabaseCorruptionError):
            core._verify_sqlite_quick_check(engine, database)
    finally:
        engine.dispose()


def test_integrity_check_reports_healthy_database_with_uri_characters(tmp_path: Path) -> None:
    from backend.db.recovery import sqlite_integrity_check

    database = tmp_path / "wireloft test.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE example (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO example(value) VALUES ('ok')")
        connection.commit()
    finally:
        connection.close()

    assert sqlite_integrity_check(database) == ("ok",)


def test_scheduler_pauses_after_database_corruption(monkeypatch, caplog) -> None:
    import task_manager.scheduler.executor as executor_module
    import task_manager.scheduler.scheduler as scheduler_module
    from backend.db import DatabaseCorruptionError

    class FakeScheduler:
        running = True

        def __init__(self):
            self.paused = False

        def pause(self):
            self.paused = True

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(scheduler_module, "_scheduler", fake_scheduler)

    def corrupted(**_kwargs):
        raise DatabaseCorruptionError("database disk image is malformed")

    monkeypatch.setattr(executor_module, "execute_task", corrupted)
    caplog.set_level(logging.CRITICAL)

    scheduler_module.execute_task_job(
        def_key="test",
        resource_type="show",
        resource_id=1,
    )

    assert fake_scheduler.paused
    assert "scheduled background work has been paused" in caplog.text
