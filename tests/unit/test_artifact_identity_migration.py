from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


_PREVIOUS_REVISION = "e3a1b5c7d902"
_ARTIFACT_IDENTITY_REVISION = "c1f7b9e4d205"


@pytest.fixture
def migration_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.db import core

    database_path = tmp_path / "artifact-identity-migration.db"
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


def _insert_available_download(engine, path: Path) -> int:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "INSERT INTO media_downloads "
                "(type, media_item_id, local_media_profile_id, file_path, artifact_status, "
                "automatic_retry_suppressed) VALUES "
                "('episode', 1, 1, :path, 'available', 0)"
            ),
            {"path": str(path)},
        )
        return int(result.lastrowid)


def test_migration_backfills_existing_download_and_enforces_identity(migration_database, tmp_path):
    _database_path, engine = migration_database
    from backend.db.migrations import get_alembic_config
    from backend.utils.artifact_identity import inspect_artifact

    command.upgrade(get_alembic_config(), _PREVIOUS_REVISION)
    artifact = tmp_path / "existing.m4a"
    artifact.write_bytes(b"existing downloaded media")
    download_id = _insert_available_download(engine, artifact)
    expected = inspect_artifact(artifact)

    command.upgrade(get_alembic_config(), _ARTIFACT_IDENTITY_REVISION)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT artifact_stat_dev, artifact_stat_ino, artifact_size_bytes, "
                "artifact_fingerprint FROM media_downloads WHERE id = :download_id"
            ),
            {"download_id": download_id},
        ).mappings().one()

    assert row["artifact_stat_dev"] == expected.stat_dev
    assert row["artifact_stat_ino"] == expected.stat_ino
    assert row["artifact_size_bytes"] == expected.size_bytes
    assert row["artifact_fingerprint"] == expected.fingerprint

    column_names = {column["name"] for column in inspect(engine).get_columns("media_downloads")}
    assert {
        "artifact_stat_dev",
        "artifact_stat_ino",
        "artifact_size_bytes",
        "artifact_fingerprint",
    } <= column_names

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO media_downloads "
                    "(type, media_item_id, local_media_profile_id, file_path, artifact_status, "
                    "automatic_retry_suppressed) VALUES "
                    "('episode', 2, 1, '/tmp/invalid.m4a', 'available', 0)"
                )
            )

    # Desired downloads and already-missing artifacts have no inspectable file,
    # so these states legitimately allow the identity tuple to remain NULL.
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO media_downloads "
                "(type, media_item_id, local_media_profile_id, file_path, artifact_status, "
                "automatic_retry_suppressed) VALUES "
                "('episode', 3, 1, '/tmp/not-downloaded.m4a', 'absent', 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO media_downloads "
                "(type, media_item_id, local_media_profile_id, file_path, artifact_status, "
                "automatic_retry_suppressed) VALUES "
                "('episode', 4, 1, '/tmp/already-missing.m4a', 'missing', 0)"
            )
        )


def test_migration_marks_missing_existing_artifact_instead_of_blocking_upgrade(migration_database, tmp_path):
    _database_path, engine = migration_database
    from backend.db.migrations import get_alembic_config, get_current_revisions

    command.upgrade(get_alembic_config(), _PREVIOUS_REVISION)
    missing = tmp_path / "already-missing.m4a"
    download_id = _insert_available_download(engine, missing)

    command.upgrade(get_alembic_config(), _ARTIFACT_IDENTITY_REVISION)

    assert get_current_revisions() == (_ARTIFACT_IDENTITY_REVISION,)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT artifact_status, artifact_error, artifact_stat_dev, artifact_stat_ino, "
                "artifact_size_bytes, artifact_fingerprint "
                "FROM media_downloads WHERE id = :download_id"
            ),
            {"download_id": download_id},
        ).mappings().one()

    assert row["artifact_status"] == "missing"
    assert "File not found" in row["artifact_error"]
    assert row["artifact_stat_dev"] is None
    assert row["artifact_stat_ino"] is None
    assert row["artifact_size_bytes"] is None
    assert row["artifact_fingerprint"] is None

    column_names = {column["name"] for column in inspect(engine).get_columns("media_downloads")}
    assert "artifact_fingerprint" in column_names
