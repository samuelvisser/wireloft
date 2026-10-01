from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_auxiliary_asset_migration_preserves_thumbnail_without_filesystem_access():
    migration = import_module(
        "backend.db.alembic.versions.f2a6c93d8b14_wireloft_1_2_1"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE media_downloads "
            "(id INTEGER PRIMARY KEY, thumbnail_path TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO media_downloads VALUES "
            "(1, '/unmounted/Movie.jpg'), (2, NULL)"
        ))

        with Operations.context(MigrationContext.configure(connection)):
            migration._upgrade_download_assets()

        assets = connection.execute(text(
            "SELECT media_download_id, asset_key, kind, path, suffix "
            "FROM media_download_assets ORDER BY asset_key"
        )).all()
        assert assets == [
            (1, "artwork", "thumbnail", "/unmounted/Movie.jpg", ".jpg")
        ]
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("media_downloads")
        }
        assert columns == {"id"}

        with Operations.context(MigrationContext.configure(connection)):
            migration._downgrade_download_assets()

        assert connection.execute(text(
            "SELECT thumbnail_path FROM media_downloads WHERE id=1"
        )).scalar_one() == "/unmounted/Movie.jpg"
        assert "media_download_assets" not in inspect(connection).get_table_names()

    engine.dispose()
