"""Verify the global episode scans move from show 0 to no resource."""
from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_global_scan_migration_clears_show_zero_only_for_global_scans():
    migration = import_module(
        "backend.db.alembic.versions.e566c9fe464d_wireloft_1_3_0"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE task_definitions (id INTEGER PRIMARY KEY, key VARCHAR(120))"))
        connection.execute(text("CREATE TABLE task_runs (id INTEGER PRIMARY KEY, definition_id INTEGER, resource_id INTEGER)"))
        connection.execute(text(
            "CREATE TABLE task_operation_targets (id INTEGER PRIMARY KEY, task_key VARCHAR(120), resource_id INTEGER)"
        ))
        connection.execute(text(
            "INSERT INTO task_definitions (id, key) VALUES (1, 'fetch_new_episodes'), (2, 'file_watcher')"
        ))
        connection.execute(text(
            "INSERT INTO task_runs (id, definition_id, resource_id) VALUES (1, 1, 0), (2, 1, 7), (3, 2, 0)"
        ))
        connection.execute(text(
            "INSERT INTO task_operation_targets (id, task_key, resource_id) VALUES "
            "(1, 'fetch_new_episodes', 0), (2, 'fetch_new_episodes', 7), (3, 'file_watcher', 0)"
        ))

        with Operations.context(MigrationContext.configure(connection)):
            migration._set_global_scan_resource_id("= 0", "NULL")

        assert connection.execute(text("SELECT id, resource_id FROM task_runs ORDER BY id")).all() == [
            (1, None), (2, 7), (3, 0),
        ]
        assert connection.execute(text(
            "SELECT id, resource_id FROM task_operation_targets ORDER BY id"
        )).all() == [(1, None), (2, 7), (3, 0)]

        with Operations.context(MigrationContext.configure(connection)):
            migration._set_global_scan_resource_id("IS NULL", "0")

        assert connection.execute(text("SELECT id, resource_id FROM task_runs ORDER BY id")).all() == [
            (1, 0), (2, 7), (3, 0),
        ]
