from __future__ import annotations

import importlib
import json

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_prerelease_download_batch_manifest_migrates_to_operation_dependencies(tmp_path, monkeypatch):
    database = tmp_path / "legacy-batch.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")

    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE task_operations (
                id VARCHAR(36) PRIMARY KEY,
                status VARCHAR(24) NOT NULL,
                progress INTEGER,
                message TEXT,
                finished_at DATETIME
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE task_runs (
                id INTEGER PRIMARY KEY,
                status VARCHAR(24) NOT NULL,
                message TEXT,
                finished_at DATETIME,
                next_retry_at DATETIME
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE task_operation_targets (
                id INTEGER PRIMARY KEY,
                operation_id VARCHAR(36) NOT NULL,
                task_key VARCHAR(120) NOT NULL
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE task_operation_runs (
                target_id INTEGER NOT NULL,
                task_run_id INTEGER NOT NULL,
                operation_id VARCHAR(36) NOT NULL
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE download_batch_items (
                id INTEGER PRIMARY KEY,
                owner_key VARCHAR(80) NOT NULL,
                owner_run_id INTEGER,
                owner_operation_id VARCHAR(36),
                media_download_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                weight BIGINT NOT NULL,
                child_operation_id VARCHAR(36),
                owns_operation BOOLEAN NOT NULL DEFAULT 0,
                prepared BOOLEAN NOT NULL DEFAULT 0,
                error TEXT
            )
        """)

        connection.execute(text("""
            INSERT INTO task_operations (id, status, progress, message)
            VALUES
                ('parent', 'RUNNING', 35, 'Coordinating'),
                ('child', 'RUNNING', 40, 'Downloading')
        """))
        connection.execute(text("""
            INSERT INTO task_runs (id, status, message)
            VALUES (1, 'RUNNING', 'Coordinating')
        """))
        connection.execute(text("""
            INSERT INTO task_operation_targets (id, operation_id, task_key)
            VALUES (1, 'parent', 'media_download_bulk_action_worker')
        """))
        connection.execute(text("""
            INSERT INTO task_operation_runs (target_id, task_run_id, operation_id)
            VALUES (1, 1, 'parent')
        """))
        connection.execute(text("""
            INSERT INTO download_batch_items (
                id, owner_key, owner_run_id, owner_operation_id,
                media_download_id, title, weight, child_operation_id,
                owns_operation, prepared
            ) VALUES (
                1, 'operation:parent:generation:0', 1, 'parent',
                42, 'Episode', 123, 'child', 1, 1
            )
        """))

        migration = importlib.import_module(
            "backend.db.alembic.versions.f7a3c91d2e84_operation_dependencies"
        )
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(migration, "op", Operations(context))
        migration.upgrade()

    inspector = inspect(engine)
    try:
        assert "download_batch_items" not in inspector.get_table_names()
        assert "completion_progress" in {
            column["name"] for column in inspector.get_columns("task_operations")
        }

        with engine.connect() as connection:
            dependency = connection.execute(text("""
                SELECT child_operation_id, slot_key, weight, required,
                       cancel_policy, context
                FROM task_operation_dependencies
                WHERE parent_operation_id = 'parent'
            """)).mappings().one()
            assert dependency["child_operation_id"] == "child"
            assert dependency["slot_key"] == "media_download:42"
            assert dependency["weight"] == 123
            assert bool(dependency["required"])
            assert dependency["cancel_policy"] == "cancel_if_exclusive"
            assert json.loads(dependency["context"]) == {
                "media_download_id": 42,
                "captured_size_bytes": 123,
            }

            assert connection.execute(text(
                "SELECT COUNT(*) FROM task_operation_targets WHERE operation_id = 'parent'"
            )).scalar_one() == 0
            assert connection.execute(text(
                "SELECT status FROM task_runs WHERE id = 1"
            )).scalar_one() == "CANCELED"
    finally:
        engine.dispose()
