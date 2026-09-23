from __future__ import annotations

import importlib

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select


def _thumbnail_table(name: str, metadata: MetaData) -> Table:
    return Table(
        name,
        metadata,
        Column("id", Integer, primary_key=True),
        Column("thumbnail_landscape_path", String, nullable=True),
        Column("thumbnail_portrait_path", String, nullable=True),
        Column("thumbnail_square_path", String, nullable=True),
    )


def _rows_by_id(connection, table: Table):
    return {
        row.id: row
        for row in connection.execute(select(table).order_by(table.c.id))
    }


def test_thumbnail_alias_migration_uses_media_type_default_orientations():
    migration = importlib.import_module(
        "backend.db.alembic.versions.4e6c9a1b7d2f_normalize_thumbnail_aliases"
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    shows = _thumbnail_table("shows", metadata)
    episodes = _thumbnail_table("media_items_episode", metadata)
    movies = _thumbnail_table("media_items_movie", metadata)
    movie_extras = _thumbnail_table("movie_extra_sources", metadata)
    metadata.create_all(engine)

    portrait_default_rows = [
        {
            "id": 1,
            "thumbnail_landscape_path": "portrait.jpg",
            "thumbnail_portrait_path": "portrait.jpg",
            "thumbnail_square_path": "portrait.jpg",
        },
        {
            "id": 2,
            "thumbnail_landscape_path": "image.jpg",
            "thumbnail_portrait_path": "image.jpg?auto=compress",
            "thumbnail_square_path": "square.jpg",
        },
    ]
    landscape_default_rows = [
        {
            "id": 1,
            "thumbnail_landscape_path": "landscape.jpg",
            "thumbnail_portrait_path": "landscape.jpg",
            "thumbnail_square_path": "landscape.jpg",
        },
        {
            "id": 2,
            "thumbnail_landscape_path": "image.jpg",
            "thumbnail_portrait_path": "image.jpg?auto=compress",
            "thumbnail_square_path": "square.jpg",
        },
    ]

    with engine.begin() as connection:
        connection.execute(shows.insert(), portrait_default_rows)
        connection.execute(movies.insert(), portrait_default_rows)
        connection.execute(episodes.insert(), landscape_default_rows)
        connection.execute(movie_extras.insert(), landscape_default_rows)

        migration._normalize_thumbnail_aliases(connection)

        for table in (shows, movies):
            rows = _rows_by_id(connection, table)
            assert rows[1].thumbnail_portrait_path == "portrait.jpg"
            assert rows[1].thumbnail_landscape_path is None
            assert rows[1].thumbnail_square_path is None
            assert rows[2].thumbnail_portrait_path == "image.jpg?auto=compress"
            assert rows[2].thumbnail_landscape_path == "image.jpg"
            assert rows[2].thumbnail_square_path == "square.jpg"

        for table in (episodes, movie_extras):
            rows = _rows_by_id(connection, table)
            assert rows[1].thumbnail_landscape_path == "landscape.jpg"
            assert rows[1].thumbnail_portrait_path is None
            assert rows[1].thumbnail_square_path is None
            assert rows[2].thumbnail_landscape_path == "image.jpg"
            assert rows[2].thumbnail_portrait_path == "image.jpg?auto=compress"
            assert rows[2].thumbnail_square_path == "square.jpg"

    engine.dispose()
