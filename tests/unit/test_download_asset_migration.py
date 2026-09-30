from importlib import import_module
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text, inspect


def test_auxiliary_asset_migration_preserves_paths_without_filesystem_access():
    migration = import_module('backend.db.alembic.versions.c2e97bfa608d_download_auxiliary_assets')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE task_runs (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE task_operations (id TEXT PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE media_downloads (id INTEGER PRIMARY KEY, thumbnail_path TEXT, nfo_path TEXT)'))
        connection.execute(text("INSERT INTO media_downloads VALUES (1, '/unmounted/Movie.jpg', '/unmounted/Movie.nfo'), (2, NULL, NULL)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assets = connection.execute(text('SELECT media_download_id, asset_key, path, suffix FROM media_download_assets ORDER BY asset_key')).all()
        assert assets == [(1, 'artwork', '/unmounted/Movie.jpg', '.jpg'), (1, 'nfo', '/unmounted/Movie.nfo', '.nfo')]
        columns = {column['name'] for column in inspect(connection).get_columns('media_downloads')}
        assert columns == {'id'}
        assert 'owner_operation_id' in {column['name'] for column in inspect(connection).get_columns('download_batch_items')}
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert connection.execute(text('SELECT thumbnail_path, nfo_path FROM media_downloads WHERE id=1')).one() == ('/unmounted/Movie.jpg', '/unmounted/Movie.nfo')
    engine.dispose()
