from __future__ import annotations

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_show_assets_upgrade_downgrade_and_foreign_keys():
    migration = importlib.import_module("backend.db.alembic.versions.a9d73b8e5f21_show_local_assets")
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE shows (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE local_media_profiles (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE local_media_profiles_show (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO shows VALUES (1)")
        connection.exec_driver_sql("INSERT INTO local_media_profiles VALUES (2)")
        connection.exec_driver_sql("INSERT INTO local_media_profiles_show VALUES (2)")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.exec_driver_sql("SELECT download_show_assets FROM local_media_profiles_show").scalar() == 0
        connection.exec_driver_sql("INSERT INTO local_media_profiles_show (id) VALUES (3)")
        assert connection.exec_driver_sql(
            "SELECT download_show_assets FROM local_media_profiles_show WHERE id=3"
        ).scalar() is None
        connection.exec_driver_sql("INSERT INTO show_local_assets (show_id,local_media_profile_id,asset_type,file_path) VALUES (1,2,'poster','/downloads/show/poster.jpg')")
        connection.exec_driver_sql("DELETE FROM shows WHERE id=1")
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM show_local_assets").scalar() == 0
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "show_local_assets" not in sa.inspect(connection).get_table_names()
        assert [column["name"] for column in sa.inspect(connection).get_columns("local_media_profiles_show")] == ["id"]
        assert connection.exec_driver_sql("SELECT id FROM local_media_profiles_show").scalar() == 2
    engine.dispose()



def test_show_asset_source_format_migration_upgrade_and_downgrade():
    base_migration = importlib.import_module("backend.db.alembic.versions.a9d73b8e5f21_show_local_assets")
    migration = importlib.import_module("backend.db.alembic.versions.f4c2a8d19e73_show_asset_source_format")
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE shows (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE local_media_profiles (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE local_media_profiles_show (id INTEGER PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(connection)):
            base_migration.upgrade()
            migration.upgrade()
        columns = {column["name"] for column in sa.inspect(connection).get_columns("show_local_assets")}
        assert "source_format" in columns
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        columns = {column["name"] for column in sa.inspect(connection).get_columns("show_local_assets")}
        assert "source_format" not in columns
    engine.dispose()
