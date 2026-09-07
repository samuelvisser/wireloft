from importlib import import_module

from sqlalchemy import create_engine, text


migration = import_module(
    "backend.db.alembic.versions.a4d7c2e9f610_canonicalize_episode_lifecycle_metadata"
)


def _create_metadata_table(connection) -> None:
    connection.execute(text(
        "CREATE TABLE metadata ("
        "id INTEGER PRIMARY KEY, parent_table TEXT NOT NULL, parent_id INTEGER NOT NULL, "
        "key TEXT NOT NULL, value TEXT NOT NULL, "
        "UNIQUE(parent_table, parent_id, key))"
    ))


def test_lifecycle_metadata_migration_moves_legacy_keys_to_canonical_names():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _create_metadata_table(connection)
        connection.execute(text(
            "INSERT INTO metadata (id,parent_table,parent_id,key,value) VALUES "
            "(1,'episodes',10,'dw_processing.reason','not_found'),"
            "(2,'episodes',10,'dw_processing.since','2026-09-07T10:00:00+00:00')"
        ))

        for old, new in migration._METADATA_RENAMES.items():
            migration._migrate_metadata_key(connection, old, new)

        rows = connection.execute(text(
            "SELECT id,key,value FROM metadata ORDER BY id"
        )).all()

    assert rows == [
        (1, "no_usable_media.reason", "not_found"),
        (2, "no_usable_media.since", "2026-09-07T10:00:00+00:00"),
    ]


def test_lifecycle_metadata_migration_keeps_existing_canonical_values_and_removes_legacy_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _create_metadata_table(connection)
        connection.execute(text(
            "INSERT INTO metadata (id,parent_table,parent_id,key,value) VALUES "
            "(1,'episodes',10,'no_usable_media.reason','no_show_today'),"
            "(2,'episodes',10,'dw_processing.reason','not_found'),"
            "(3,'episodes',10,'no_usable_media.since','2026-09-07T09:00:00+00:00'),"
            "(4,'episodes',10,'dw_processing.since','2026-09-07T10:00:00+00:00'),"
            "(5,'shows',10,'dw_processing.reason','unrelated')"
        ))

        for old, new in migration._METADATA_RENAMES.items():
            migration._migrate_metadata_key(connection, old, new)

        episode_rows = connection.execute(text(
            "SELECT key,value FROM metadata WHERE parent_table='episodes' ORDER BY key"
        )).all()
        show_rows = connection.execute(text(
            "SELECT key,value FROM metadata WHERE parent_table='shows'"
        )).all()

    assert episode_rows == [
        ("no_usable_media.reason", "no_show_today"),
        ("no_usable_media.since", "2026-09-07T09:00:00+00:00"),
    ]
    assert show_rows == [("dw_processing.reason", "unrelated")]
