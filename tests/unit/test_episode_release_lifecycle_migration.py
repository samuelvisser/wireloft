from importlib import import_module

from sqlalchemy import create_engine, text


migration = import_module(
    "backend.db.alembic.versions.e6a9c1f4b203_episode_release_lifecycle"
)


def _create_task_tables(connection) -> None:
    connection.execute(text(
        "CREATE TABLE task_definitions ("
        "id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, title TEXT, description TEXT, "
        "allowed_resource_types TEXT, default_max_retries INTEGER)"
    ))
    connection.execute(text(
        "CREATE TABLE task_runs (id INTEGER PRIMARY KEY, definition_id INTEGER NOT NULL)"
    ))
    connection.execute(text(
        "CREATE TABLE task_schedules (id INTEGER PRIMARY KEY, definition_id INTEGER NOT NULL)"
    ))
    connection.execute(text(
        "CREATE TABLE task_operation_targets ("
        "id INTEGER PRIMARY KEY, operation_id TEXT NOT NULL, task_key TEXT NOT NULL, slot_key TEXT NOT NULL)"
    ))


def test_task_key_migration_merges_existing_new_definition_without_losing_history():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _create_task_tables(connection)
        connection.execute(text(
            "INSERT INTO task_definitions (id,key,title) VALUES "
            "(1,'monitor_episode_worker','Old monitor'),"
            "(2,'monitor_pending_episode','New monitor')"
        ))
        connection.execute(text(
            "INSERT INTO task_runs (id,definition_id) VALUES (10,1),(11,2)"
        ))
        connection.execute(text(
            "INSERT INTO task_schedules (id,definition_id) VALUES (20,1),(21,2)"
        ))
        connection.execute(text(
            "INSERT INTO task_operation_targets (id,operation_id,task_key,slot_key) VALUES "
            "(30,'old-op','monitor_episode_worker','monitor_episode_worker:episode:5'),"
            "(31,'new-op','monitor_pending_episode','monitor_pending_episode:episode:6')"
        ))

        migration._migrate_task_key(
            connection,
            "monitor_episode_worker",
            "monitor_pending_episode",
        )

        definitions = connection.execute(text(
            "SELECT id,key FROM task_definitions ORDER BY id"
        )).all()
        runs = connection.execute(text(
            "SELECT definition_id FROM task_runs ORDER BY id"
        )).scalars().all()
        schedules = connection.execute(text(
            "SELECT definition_id FROM task_schedules ORDER BY id"
        )).scalars().all()
        targets = connection.execute(text(
            "SELECT task_key,slot_key FROM task_operation_targets ORDER BY id"
        )).all()

    assert definitions == [(1, "monitor_pending_episode")]
    assert runs == [1, 1]
    assert schedules == [1, 1]
    assert targets == [
        ("monitor_pending_episode", "monitor_pending_episode:episode:5"),
        ("monitor_pending_episode", "monitor_pending_episode:episode:6"),
    ]


def test_task_key_migration_still_renames_when_target_definition_does_not_exist():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _create_task_tables(connection)
        connection.execute(text(
            "INSERT INTO task_definitions (id,key,title) VALUES "
            "(1,'refresh_episode_metadata_worker','Refresh metadata')"
        ))

        migration._migrate_task_key(
            connection,
            "refresh_episode_metadata_worker",
            "refresh_episode_metadata",
        )

        definitions = connection.execute(text(
            "SELECT id,key FROM task_definitions"
        )).all()

    assert definitions == [(1, "refresh_episode_metadata")]
