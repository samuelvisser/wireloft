"""Verify the WireLoft 1.2.5 subtitle defaults follow existing profile scope."""
from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_subtitle_migration_uses_existing_profile_scope():
    migration = import_module(
        "backend.db.alembic.versions.c4e93f1a2b6d_wireloft_1_2_5"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE local_media_profiles ("
            "id INTEGER PRIMARY KEY, type VARCHAR(24) NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE local_media_profiles_show ("
            "id INTEGER PRIMARY KEY, show_scope VARCHAR(24) NOT NULL)"
        ))
        profiles = [
            (1, "movie", None),
            (2, "show", "both"),
            (3, "show", "series"),
            (4, "show", "podcast"),
        ]
        for profile_id, kind, scope in profiles:
            connection.execute(text(
                "INSERT INTO local_media_profiles (id, type) VALUES (:id, :kind)"
            ), {"id": profile_id, "kind": kind})
            if scope:
                connection.execute(text(
                    "INSERT INTO local_media_profiles_show (id, show_scope) "
                    "VALUES (:id, :scope)"
                ), {"id": profile_id, "scope": scope})

        with Operations.context(MigrationContext.configure(connection)):
            migration._upgrade_subtitle_mode()

        stored = connection.execute(text(
            "SELECT id, subtitle_mode FROM local_media_profiles ORDER BY id"
        )).all()
        assert stored == [
            (1, "sidecar"),
            (2, "sidecar"),
            (3, "sidecar"),
            (4, "no_subtitles"),
        ]
        default = next(
            column["default"] for column in inspect(connection).get_columns("local_media_profiles")
            if column["name"] == "subtitle_mode"
        )
        assert default == "'sidecar'"

        with Operations.context(MigrationContext.configure(connection)):
            migration._downgrade_subtitle_mode()
        assert "subtitle_mode" not in {
            col["name"] for col in inspect(connection).get_columns("local_media_profiles")
        }
    engine.dispose()
