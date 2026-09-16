from __future__ import annotations

from sqlalchemy import create_engine, event, text


def test_shared_sqlite_connections_enable_foreign_keys(tmp_path):
    from backend.db.core import _configure_sqlite_connection

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'foreign-keys.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _configure_sqlite_connection)

    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        engine.dispose()


def test_integrity_migration_repairs_legacy_orphans(tmp_path):
    from backend.db.alembic.versions.a4e7d18c2f90_sqlite_foreign_key_integrity import (
        _delete_broken_scheduler_foreign_keys,
        _delete_orphaned_media_download_subtypes,
        _delete_orphaned_polymorphic_resources,
    )

    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy-orphans.db').as_posix()}")
    try:
        with engine.begin() as connection:
            for table_name in (
                "shows",
                "seasons",
                "media_items_episode",
                "media_items_movie",
                "media_items_movie_extra",
                "media_downloads",
                "download_profiles",
            ):
                connection.execute(text(
                    f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
                ))

            for table_name in (
                "media_downloads_episode",
                "media_downloads_movie",
                "media_downloads_movie_extra",
            ):
                connection.execute(text(
                    f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
                ))

            connection.execute(text(
                "CREATE TABLE task_operations ("
                "id VARCHAR(36) PRIMARY KEY, resource_type VARCHAR(80), resource_id INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE task_operation_targets ("
                "id INTEGER PRIMARY KEY, operation_id VARCHAR(36), "
                "resource_type VARCHAR(80), resource_id INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE task_runs ("
                "id INTEGER PRIMARY KEY, resource_type VARCHAR(80), resource_id INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE task_operation_runs ("
                "target_id INTEGER, task_run_id INTEGER, operation_id VARCHAR(36))"
            ))
            connection.execute(text(
                "CREATE TABLE task_schedules ("
                "id INTEGER PRIMARY KEY, resource_type VARCHAR(80), resource_id INTEGER)"
            ))

            connection.execute(text("INSERT INTO media_downloads (id) VALUES (1)"))
            for table_name in (
                "media_downloads_episode",
                "media_downloads_movie",
                "media_downloads_movie_extra",
            ):
                connection.execute(text(
                    f"INSERT INTO {table_name} (id) VALUES (1), (2)"
                ))

            connection.execute(text(
                "INSERT INTO task_operations (id, resource_type, resource_id) VALUES "
                "('kept', 'media_download', 1), "
                "('stale-download', 'media_download', 2), "
                "('unrelated', 'local_media_profile', 999)"
            ))
            connection.execute(text(
                "INSERT INTO task_operation_targets "
                "(id, operation_id, resource_type, resource_id) VALUES "
                "(1, 'kept', 'media_download', 1), "
                "(2, 'stale-download', 'media_download', 2), "
                "(3, 'missing-operation', 'media_download', 2), "
                "(4, 'kept', 'episode', 999)"
            ))
            connection.execute(text(
                "INSERT INTO task_runs (id, resource_type, resource_id) VALUES "
                "(1, 'MEDIA_DOWNLOAD', 1), "
                "(2, 'MEDIA_DOWNLOAD', 2), "
                "(3, 'SHOW', 999)"
            ))
            connection.execute(text(
                "INSERT INTO task_operation_runs "
                "(target_id, task_run_id, operation_id) VALUES "
                "(1, 1, 'kept'), "
                "(2, 2, 'stale-download'), "
                "(3, 1, 'missing-operation'), "
                "(1, 999, 'kept'), "
                "(4, 1, 'kept')"
            ))
            connection.execute(text(
                "INSERT INTO task_schedules (id, resource_type, resource_id) VALUES "
                "(1, 'MEDIA_DOWNLOAD', 1), (2, 'MEDIA_DOWNLOAD', 2)"
            ))

            _delete_broken_scheduler_foreign_keys(connection)
            _delete_orphaned_polymorphic_resources(connection)
            _delete_orphaned_media_download_subtypes(connection)

            assert connection.execute(text(
                "SELECT id FROM task_operations ORDER BY id"
            )).scalars().all() == ["kept", "unrelated"]
            assert connection.execute(text(
                "SELECT id FROM task_operation_targets ORDER BY id"
            )).scalars().all() == [1]
            assert connection.execute(text(
                "SELECT id FROM task_runs ORDER BY id"
            )).scalars().all() == [1]
            assert connection.execute(text(
                "SELECT target_id, task_run_id, operation_id FROM task_operation_runs"
            )).all() == [(1, 1, "kept")]
            assert connection.execute(text(
                "SELECT id FROM task_schedules ORDER BY id"
            )).scalars().all() == [1]

            for table_name in (
                "media_downloads_episode",
                "media_downloads_movie",
                "media_downloads_movie_extra",
            ):
                assert connection.execute(text(
                    f"SELECT id FROM {table_name} ORDER BY id"
                )).scalars().all() == [1]
    finally:
        engine.dispose()
