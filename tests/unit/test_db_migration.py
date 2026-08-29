from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def migration_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the shared DB layer at a disposable SQLite file."""
    from backend.db import core

    database_path = tmp_path / "wireloft-migration-test.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    yield database_path, engine
    engine.dispose()


def test_fresh_database_upgrades_to_head(migration_database):
    database_path, engine = migration_database

    from backend.db.migrations import get_database_status, upgrade_database

    assert not database_path.exists()

    upgrade_database()

    current, head = get_database_status()
    assert current == (head,)
    assert head == "0001"

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "alembic_version",
        "shows",
        "episodes",
        "movies",
        "media_downloads",
        "media_downloads_movie",
        "task_schedules",
        "task_runs",
    } <= tables

    movie_columns = {column["name"] for column in inspector.get_columns("movies")}
    assert movie_columns == {
        "id",
        "dw_id",
        "slug",
        "rating",
        "sharing_url",
        "license_start_date",
        "license_end_date",
        "available_in_watchlist",
    }

    movie_indexes = {index["name"]: index for index in inspector.get_indexes("movies")}
    assert "ix_movies_dw_id" in movie_indexes
    assert bool(movie_indexes["ix_movies_dw_id"]["unique"])


def test_upgrade_is_idempotent(migration_database):
    _database_path, _engine = migration_database

    from backend.db.migrations import get_database_status, upgrade_database

    upgrade_database()
    first_status = get_database_status()

    upgrade_database()

    assert get_database_status() == first_status


def test_unmanaged_existing_database_is_rejected(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import DatabaseMigrationError, upgrade_database

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE legacy_table (id INTEGER PRIMARY KEY)"))

    with pytest.raises(DatabaseMigrationError, match="not Alembic-managed"):
        upgrade_database()

    tables = set(inspect(engine).get_table_names())
    assert "legacy_table" in tables
    assert "alembic_version" not in tables


def test_initial_migration_matches_current_orm_metadata(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import check_database, upgrade_database

    upgrade_database()

    # APScheduler owns this table independently in the same SQLite file. Its
    # presence must not make Alembic think a WireLoft migration is missing.
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE apscheduler_jobs ("
                "id VARCHAR(191) PRIMARY KEY, next_run_time FLOAT, job_state BLOB NOT NULL)"
            )
        )

    check_database()


def test_migration_history_has_exactly_one_head():
    from backend.db.migrations import get_head_revisions

    assert get_head_revisions() == ("0001",)
