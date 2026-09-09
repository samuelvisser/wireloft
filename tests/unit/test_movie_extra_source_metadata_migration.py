from __future__ import annotations

import json
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


SOURCE_IDENTITY_REVISION = "f7c2a5d9e104"
SOURCE_METADATA_REVISION = "e8d1c4b7a205"


def _insert_media_item(
    connection,
    *,
    uuid: str,
    media_type: str,
    title: str,
    description: str | None = None,
    duration: float = 60,
    background_image_path: str | None = None,
    thumbnail_landscape_path: str | None = None,
    thumbnail_portrait_path: str | None = None,
    thumbnail_square_path: str | None = None,
) -> int:
    return connection.execute(text(
        "INSERT INTO media_items "
        "(uuid, type, title, description, downloaded_date, duration, "
        "background_image_path, thumbnail_landscape_path, "
        "thumbnail_portrait_path, thumbnail_square_path) VALUES "
        "(:uuid, :type, :title, :description, NULL, :duration, "
        ":background, :landscape, :portrait, :square)"
    ), {
        "uuid": uuid,
        "type": media_type,
        "title": title,
        "description": description,
        "duration": duration,
        "background": background_image_path,
        "landscape": thumbnail_landscape_path,
        "portrait": thumbnail_portrait_path,
        "square": thumbnail_square_path,
    }).lastrowid


def _json_list(value) -> list[str]:
    if isinstance(value, list):
        return value
    return json.loads(value) if value else []


def test_metadata_migration_deduplicates_values_without_rewriting_placements(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.db import core
    from backend.db.migrations import get_alembic_config

    database_path = tmp_path / "movie-extra-source-metadata.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    command.upgrade(get_alembic_config(), SOURCE_IDENTITY_REVISION)

    with engine.begin() as connection:
        profile_id = connection.execute(text(
            "INSERT INTO local_media_profiles "
            "(type, slug, name, output_template, preferred_format, append_media_type_to_filename) "
            "VALUES ('movie', 'movies', 'Movies', '/downloads/{{ movie_title }}/{{ slug }}.ext', "
            "'format_1080p', 0)"
        )).lastrowid
        connection.execute(
            text("INSERT INTO local_media_profiles_movie (id) VALUES (:id)"),
            {"id": profile_id},
        )

        movie_a_id = _insert_media_item(
            connection,
            uuid="movie-a-uuid",
            media_type="movie",
            title="Movie A",
        )
        movie_b_id = _insert_media_item(
            connection,
            uuid="movie-b-uuid",
            media_type="movie",
            title="Movie B",
        )
        connection.execute(
            text("INSERT INTO movies (id, slug) VALUES (:id, 'movie-a')"),
            {"id": movie_a_id},
        )
        connection.execute(
            text("INSERT INTO movies (id, slug) VALUES (:id, 'movie-b')"),
            {"id": movie_b_id},
        )

        source_id = connection.execute(text(
            "INSERT INTO movie_extra_sources (slug) VALUES ('shared-extra')"
        )).lastrowid

        extra_a_id = _insert_media_item(
            connection,
            uuid="extra-a-uuid",
            media_type="movie_extra",
            title="Shared Extra",
            description="Canonical description",
            duration=95,
            background_image_path="background.jpg",
            thumbnail_landscape_path="landscape.jpg",
            thumbnail_portrait_path="portrait.jpg",
            thumbnail_square_path="square.jpg",
        )
        # Simulate a second parent snapshot with some missing global fields. The
        # migration should preserve the richer value available on either row.
        extra_b_id = _insert_media_item(
            connection,
            uuid="extra-b-uuid",
            media_type="movie_extra",
            title="Shared Extra",
            description=None,
            duration=95,
        )

        connection.execute(text(
            "INSERT INTO movie_extras "
            "(id, movie_id, source_id, movie_extra_type, sharing_url, published_date, available_for) "
            "VALUES (:id, :movie_id, :source_id, 'trailer', :sharing_url, "
            "'2026-09-01 12:30:00+00:00', '[\"ALL_ACCESS\"]')"
        ), {
            "id": extra_a_id,
            "movie_id": movie_a_id,
            "source_id": source_id,
            "sharing_url": "https://www.dailywire.com/videos/shared-extra",
        })
        connection.execute(text(
            "INSERT INTO movie_extras "
            "(id, movie_id, source_id, movie_extra_type, sharing_url, published_date, available_for) "
            "VALUES (:id, :movie_id, :source_id, 'scene', NULL, NULL, '[]')"
        ), {
            "id": extra_b_id,
            "movie_id": movie_b_id,
            "source_id": source_id,
        })
        connection.execute(text(
            "UPDATE movies SET official_trailer_id = :extra_id WHERE id = :movie_id"
        ), {
            "extra_id": extra_a_id,
            "movie_id": movie_a_id,
        })

        download_ids = []
        for extra_id, movie_name in (
            (extra_a_id, "Movie A"),
            (extra_b_id, "Movie B"),
        ):
            download_id = connection.execute(text(
                "INSERT INTO media_downloads "
                "(type, media_item_id, local_media_profile_id, file_path) "
                "VALUES ('movie_extra', :extra_id, :profile_id, :path)"
            ), {
                "extra_id": extra_id,
                "profile_id": profile_id,
                "path": f"/downloads/{movie_name}/shared-extra.mp4",
            }).lastrowid
            connection.execute(
                text("INSERT INTO media_downloads_movie_extra (id) VALUES (:id)"),
                {"id": download_id},
            )
            download_ids.append(download_id)

    command.upgrade(get_alembic_config(), SOURCE_METADATA_REVISION)

    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("movie_extras")} == {
        "id",
        "movie_id",
        "source_id",
        "movie_extra_type",
    }
    with engine.connect() as connection:
        source = connection.execute(text(
            "SELECT slug, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path, "
            "sharing_url, published_date, available_for "
            "FROM movie_extra_sources WHERE id = :id"
        ), {"id": source_id}).mappings().one()
        assert source["slug"] == "shared-extra"
        assert source["title"] == "Shared Extra"
        assert source["description"] == "Canonical description"
        assert source["duration"] == 95
        assert source["background_image_path"] == "background.jpg"
        assert source["thumbnail_landscape_path"] == "landscape.jpg"
        assert source["thumbnail_portrait_path"] == "portrait.jpg"
        assert source["thumbnail_square_path"] == "square.jpg"
        assert source["sharing_url"] == "https://www.dailywire.com/videos/shared-extra"
        assert source["published_date"] is not None
        assert _json_list(source["available_for"]) == ["ALL_ACCESS"]

        raw_placements = connection.execute(text(
            "SELECT id, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path "
            "FROM media_items WHERE id IN (:a, :b) ORDER BY id"
        ), {"a": extra_a_id, "b": extra_b_id}).mappings().all()
        assert [row["id"] for row in raw_placements] == [extra_a_id, extra_b_id]
        for row in raw_placements:
            assert row["title"] == ""
            assert row["description"] is None
            assert row["duration"] == 0
            assert row["background_image_path"] is None
            assert row["thumbnail_landscape_path"] is None
            assert row["thumbnail_portrait_path"] is None
            assert row["thumbnail_square_path"] is None

        assert connection.execute(text(
            "SELECT official_trailer_id FROM movies WHERE id = :id"
        ), {"id": movie_a_id}).scalar_one() == extra_a_id
        assert [row[0] for row in connection.execute(text(
            "SELECT id FROM media_downloads ORDER BY id"
        )).all()] == download_ids

    command.downgrade(get_alembic_config(), SOURCE_IDENTITY_REVISION)

    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("movie_extra_sources")} == {
        "id",
        "slug",
    }
    assert {column["name"] for column in inspector.get_columns("movie_extras")} == {
        "id",
        "movie_id",
        "source_id",
        "movie_extra_type",
        "sharing_url",
        "published_date",
        "available_for",
    }
    with engine.connect() as connection:
        restored = connection.execute(text(
            "SELECT mi.id, mi.title, mi.description, mi.duration, me.sharing_url, me.available_for "
            "FROM media_items AS mi JOIN movie_extras AS me ON me.id = mi.id "
            "WHERE mi.id IN (:a, :b) ORDER BY mi.id"
        ), {"a": extra_a_id, "b": extra_b_id}).mappings().all()
        assert [row["title"] for row in restored] == ["Shared Extra", "Shared Extra"]
        assert [row["description"] for row in restored] == [
            "Canonical description",
            "Canonical description",
        ]
        assert [row["duration"] for row in restored] == [95, 95]
        assert [row["sharing_url"] for row in restored] == [
            "https://www.dailywire.com/videos/shared-extra",
            "https://www.dailywire.com/videos/shared-extra",
        ]
        assert [_json_list(row["available_for"]) for row in restored] == [
            ["ALL_ACCESS"],
            ["ALL_ACCESS"],
        ]
        assert connection.execute(text(
            "SELECT official_trailer_id FROM movies WHERE id = :id"
        ), {"id": movie_a_id}).scalar_one() == extra_a_id
        assert connection.execute(text(
            "SELECT COUNT(*) FROM media_downloads"
        )).scalar_one() == 2

    engine.dispose()
