"""Verify scope-specific defaults and migration of removed system choices."""
from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_subtitle_scope_migration_preserves_custom_modes():
    migration = import_module(
        "backend.db.alembic.versions.c4e93f1a2b6d_subtitle_scope_defaults"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE local_media_profiles ("
            "id INTEGER PRIMARY KEY, type VARCHAR(24) NOT NULL, "
            "subtitle_mode VARCHAR(24) NOT NULL DEFAULT 'no_subtitles')"
        ))
        connection.execute(text(
            "CREATE TABLE local_media_profiles_show ("
            "id INTEGER PRIMARY KEY, show_scope VARCHAR(24) NOT NULL)"
        ))
        profiles = [
            (1, "movie", "sidecar", None),
            (2, "show", "no_subtitles", "both"),
            (3, "show", "no_subtitles", "series"),
            (4, "show", "no_subtitles", "podcast"),
            (5, "show", "embed", "series"),
            (6, "show", "system", "podcast"),
            (7, "show", "system", "both"),
            (8, "movie", "system", None),
            (9, "show", "sidecar", "podcast"),
            (10, "show", "embed_and_sidecar", "both"),
        ]
        for profile_id, kind, subtitle_mode, scope in profiles:
            connection.execute(text(
                "INSERT INTO local_media_profiles (id, type, subtitle_mode) "
                "VALUES (:id, :kind, :subtitle_mode)"
            ), {"id": profile_id, "kind": kind, "subtitle_mode": subtitle_mode})
            if scope:
                connection.execute(text(
                    "INSERT INTO local_media_profiles_show (id, show_scope) "
                    "VALUES (:id, :scope)"
                ), {"id": profile_id, "scope": scope})

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        stored = connection.execute(text(
            "SELECT id, subtitle_mode FROM local_media_profiles ORDER BY id"
        )).all()
        assert stored == [
            (1, "sidecar"),
            (2, "no_subtitles"),
            (3, "no_subtitles"),
            (4, "no_subtitles"),
            (5, "embed"),
            (6, "no_subtitles"),
            (7, "sidecar"),
            (8, "sidecar"),
            (9, "sidecar"),
            (10, "embed_and_sidecar"),
        ]
        default = next(
            column["default"] for column in inspect(connection).get_columns("local_media_profiles")
            if column["name"] == "subtitle_mode"
        )
        assert default == "'sidecar'"

        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

        restored_default = next(
            column["default"] for column in inspect(connection).get_columns("local_media_profiles")
            if column["name"] == "subtitle_mode"
        )
        assert restored_default == "'no_subtitles'"

    engine.dispose()


def test_initial_subtitle_migration_uses_existing_profile_scope():
    migration = import_module(
        "backend.db.alembic.versions.b7d31f5a2c90_subtitle_mode"
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
            migration.upgrade()

        stored = connection.execute(text(
            "SELECT id, subtitle_mode FROM local_media_profiles ORDER BY id"
        )).all()
        assert stored == [
            (1, "sidecar"),
            (2, "sidecar"),
            (3, "sidecar"),
            (4, "no_subtitles"),
        ]
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "subtitle_mode" not in {
            col["name"] for col in inspect(connection).get_columns("local_media_profiles")
        }
    engine.dispose()
