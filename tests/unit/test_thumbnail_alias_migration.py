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


def test_thumbnail_alias_migration_uses_show_and_episode_canonical_orientations():
    migration = importlib.import_module(
        "backend.db.alembic.versions.4e6c9a1b7d2f_normalize_thumbnail_aliases"
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    shows = _thumbnail_table("shows", metadata)
    episodes = _thumbnail_table("media_items_episode", metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            shows.insert(),
            [
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
            ],
        )
        connection.execute(
            episodes.insert(),
            [
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
            ],
        )

        migration._normalize_thumbnail_aliases(connection)

        show_rows = {
            row.id: row
            for row in connection.execute(select(shows).order_by(shows.c.id))
        }
        assert show_rows[1].thumbnail_portrait_path == "portrait.jpg"
        assert show_rows[1].thumbnail_landscape_path is None
        assert show_rows[1].thumbnail_square_path is None
        assert show_rows[2].thumbnail_landscape_path == "image.jpg"
        assert show_rows[2].thumbnail_portrait_path == "image.jpg?auto=compress"
        assert show_rows[2].thumbnail_square_path == "square.jpg"

        episode_rows = {
            row.id: row
            for row in connection.execute(select(episodes).order_by(episodes.c.id))
        }
        assert episode_rows[1].thumbnail_landscape_path == "landscape.jpg"
        assert episode_rows[1].thumbnail_portrait_path is None
        assert episode_rows[1].thumbnail_square_path is None
        assert episode_rows[2].thumbnail_landscape_path == "image.jpg"
        assert episode_rows[2].thumbnail_portrait_path == "image.jpg?auto=compress"
        assert episode_rows[2].thumbnail_square_path == "square.jpg"

    engine.dispose()
