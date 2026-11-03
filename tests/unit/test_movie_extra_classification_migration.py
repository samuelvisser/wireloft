from __future__ import annotations

from importlib import import_module

from sqlalchemy import create_engine, text


migration = import_module("backend.db.alembic.versions.d8b4a1f6c203_wireloft_1_1")


def test_migration_repairs_official_trailer_classification() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE media_items_movie (id INTEGER PRIMARY KEY, official_trailer_id INTEGER)"
        ))
        connection.execute(text(
            "CREATE TABLE media_items_movie_extra (id INTEGER PRIMARY KEY, movie_extra_type TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO media_items_movie_extra (id, movie_extra_type) VALUES "
            "(2, 'scene'), (3, 'scene')"
        ))
        connection.execute(text(
            "INSERT INTO media_items_movie (id, official_trailer_id) VALUES (1, 2)"
        ))

        migration._repair_movie_extra_classifications(connection)

        rows = connection.execute(text(
            "SELECT id, movie_extra_type FROM media_items_movie_extra ORDER BY id"
        )).all()

    assert rows == [(2, "trailer"), (3, "scene")]
    engine.dispose()
