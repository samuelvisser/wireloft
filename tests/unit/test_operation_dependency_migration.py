from __future__ import annotations

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_operation_dependency_schema_is_created_directly():
    migration = importlib.import_module(
        "backend.db.alembic.versions.f2a6c93d8b14_wireloft_1_2_1"
    )
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE task_operations (
                id VARCHAR(36) PRIMARY KEY,
                status VARCHAR(24) NOT NULL,
                progress INTEGER
            )
        """)
        connection.execute(text("""
            INSERT INTO task_operations (id, status, progress)
            VALUES
                ('parent', 'RUNNING', 35),
                ('child', 'RUNNING', 40),
                ('finished', 'SUCCEEDED', 87)
        """))

        with Operations.context(MigrationContext.configure(connection)):
            migration._upgrade_operation_dependencies()

        progress = connection.execute(text("""
            SELECT id, completion_progress
            FROM task_operations
            ORDER BY id
        """)).all()
        assert progress == [
            ("child", 40),
            ("finished", 100),
            ("parent", 35),
        ]

        connection.execute(text("""
            INSERT INTO task_operation_dependencies (
                parent_operation_id,
                child_operation_id,
                slot_key,
                weight,
                required,
                cancel_policy
            ) VALUES (
                'parent',
                'child',
                'media_download:42',
                123,
                1,
                'cancel_if_exclusive'
            )
        """))
        dependency = connection.execute(text("""
            SELECT child_operation_id, slot_key, weight, required, cancel_policy
            FROM task_operation_dependencies
            WHERE parent_operation_id = 'parent'
        """)).one()
        assert dependency == (
            "child",
            "media_download:42",
            123,
            1,
            "cancel_if_exclusive",
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration._downgrade_operation_dependencies()

        inspector = inspect(connection)
        assert "task_operation_dependencies" not in inspector.get_table_names()
        assert "completion_progress" not in {
            column["name"]
            for column in inspector.get_columns("task_operations")
        }

    engine.dispose()
