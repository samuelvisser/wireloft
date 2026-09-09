from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


PRE_CONTENT_REVISION = "e8d1c4b7a205"
CONTENT_REVISION = "b3e6d1f8c704"


_CONTENT_FIELDS = {
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
}


def _insert_media_item(
    connection,
    *,
    uuid: str,
    media_type: str,
    title: str,
    description: str | None,
    duration: float,
    prefix: str,
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
        "background": f"{prefix}-background.jpg" if prefix else None,
        "landscape": f"{prefix}-landscape.jpg" if prefix else None,
        "portrait": f"{prefix}-portrait.jpg" if prefix else None,
        "square": f"{prefix}-square.jpg" if prefix else None,
    }).lastrowid


def test_content_metadata_migration_preserves_media_identity_and_downloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.db import core
    from backend.db.migrations import get_alembic_config

    database_path = tmp_path / "media-content-metadata.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    command.upgrade(get_alembic_config(), PRE_CONTENT_REVISION)

    with engine.begin() as connection:
        show_id = connection.execute(text(
            "INSERT INTO shows "
            "(uuid, slug, title, description, sharing_url, membership_level, "
            "type, episode_identifier, author_name, author_slug) VALUES "
            "('show-uuid', 'show', 'Show', 'Show description', "
            "'https://example.test/show', 'FREE', 'podcast', 'numbered', "
            "'Host', 'host')"
        )).lastrowid
        season_id = connection.execute(text(
            "INSERT INTO seasons (show_id, \"index\", slug, name) "
            "VALUES (:show_id, 1, 'season-1', 'Season 1')"
        ), {"show_id": show_id}).lastrowid

        episode_id = _insert_media_item(
            connection,
            uuid="episode-uuid",
            media_type="episode",
            title="Episode Title",
            description="Episode description",
            duration=1800,
            prefix="episode",
        )
        connection.execute(text(
            "INSERT INTO episodes "
            "(id, show_id, season_id, \"index\", episode_identifier, slug, "
            "publish_status, sharing_url) VALUES "
            "(:id, :show_id, :season_id, 1, 'ep.1', 'episode-1', "
            "'published_final', 'https://example.test/episode-1')"
        ), {
            "id": episode_id,
            "show_id": show_id,
            "season_id": season_id,
        })

        movie_id = _insert_media_item(
            connection,
            uuid="movie-uuid",
            media_type="movie",
            title="Movie Title",
            description="Movie description",
            duration=5400,
            prefix="movie",
        )
        connection.execute(
            text("INSERT INTO movies (id, slug) VALUES (:id, 'movie')"),
            {"id": movie_id},
        )

        source_id = connection.execute(text(
            "INSERT INTO movie_extra_sources "
            "(slug, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path, "
            "available_for) VALUES "
            "('shared-extra', 'Shared Extra', 'Source description', 90, "
            "'source-background.jpg', 'source-landscape.jpg', "
            "'source-portrait.jpg', 'source-square.jpg', '[\"ALL_ACCESS\"]')"
        )).lastrowid
        extra_id = _insert_media_item(
            connection,
            uuid="extra-placement-uuid",
            media_type="movie_extra",
            title="",
            description=None,
            duration=0,
            prefix="",
        )
        connection.execute(text(
            "INSERT INTO movie_extras (id, movie_id, source_id, movie_extra_type) "
            "VALUES (:id, :movie_id, :source_id, 'trailer')"
        ), {
            "id": extra_id,
            "movie_id": movie_id,
            "source_id": source_id,
        })

        profile_id = connection.execute(text(
            "INSERT INTO local_media_profiles "
            "(type, slug, name, output_template, preferred_format, append_media_type_to_filename) "
            "VALUES ('movie', 'movies', 'Movies', '/downloads/{{ movie_title }}/{{ title }}.ext', "
            "'format_1080p', 0)"
        )).lastrowid
        connection.execute(
            text("INSERT INTO local_media_profiles_movie (id) VALUES (:id)"),
            {"id": profile_id},
        )
        download_id = connection.execute(text(
            "INSERT INTO media_downloads "
            "(type, media_item_id, local_media_profile_id, file_path) "
            "VALUES ('movie_extra', :extra_id, :profile_id, '/downloads/Movie/shared-extra.mp4')"
        ), {
            "extra_id": extra_id,
            "profile_id": profile_id,
        }).lastrowid
        connection.execute(
            text("INSERT INTO media_downloads_movie_extra (id) VALUES (:id)"),
            {"id": download_id},
        )

    command.upgrade(get_alembic_config(), CONTENT_REVISION)

    inspector = inspect(engine)
    assert _CONTENT_FIELDS.isdisjoint(
        {column["name"] for column in inspector.get_columns("media_items")}
    )
    assert _CONTENT_FIELDS <= {
        column["name"] for column in inspector.get_columns("episodes")
    }
    assert _CONTENT_FIELDS <= {
        column["name"] for column in inspector.get_columns("movies")
    }

    with engine.connect() as connection:
        episode = connection.execute(text(
            "SELECT title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path "
            "FROM episodes WHERE id = :id"
        ), {"id": episode_id}).mappings().one()
        assert dict(episode) == {
            "title": "Episode Title",
            "description": "Episode description",
            "duration": 1800,
            "background_image_path": "episode-background.jpg",
            "thumbnail_landscape_path": "episode-landscape.jpg",
            "thumbnail_portrait_path": "episode-portrait.jpg",
            "thumbnail_square_path": "episode-square.jpg",
        }
        movie = connection.execute(text(
            "SELECT title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path "
            "FROM movies WHERE id = :id"
        ), {"id": movie_id}).mappings().one()
        assert dict(movie) == {
            "title": "Movie Title",
            "description": "Movie description",
            "duration": 5400,
            "background_image_path": "movie-background.jpg",
            "thumbnail_landscape_path": "movie-landscape.jpg",
            "thumbnail_portrait_path": "movie-portrait.jpg",
            "thumbnail_square_path": "movie-square.jpg",
        }
        assert connection.execute(text(
            "SELECT media_item_id FROM media_downloads WHERE id = :id"
        ), {"id": download_id}).scalar_one() == extra_id
        assert connection.execute(text(
            "SELECT title FROM movie_extra_sources WHERE id = :id"
        ), {"id": source_id}).scalar_one() == "Shared Extra"

    command.downgrade(get_alembic_config(), PRE_CONTENT_REVISION)

    inspector = inspect(engine)
    assert _CONTENT_FIELDS <= {
        column["name"] for column in inspector.get_columns("media_items")
    }
    assert _CONTENT_FIELDS.isdisjoint(
        {column["name"] for column in inspector.get_columns("episodes")}
    )
    assert _CONTENT_FIELDS.isdisjoint(
        {column["name"] for column in inspector.get_columns("movies")}
    )
    with engine.connect() as connection:
        restored = connection.execute(text(
            "SELECT id, type, title, description, duration, background_image_path "
            "FROM media_items WHERE id IN (:episode, :movie, :extra) ORDER BY id"
        ), {
            "episode": episode_id,
            "movie": movie_id,
            "extra": extra_id,
        }).mappings().all()
        by_type = {row["type"]: row for row in restored}
        assert by_type["episode"]["title"] == "Episode Title"
        assert by_type["episode"]["description"] == "Episode description"
        assert by_type["episode"]["duration"] == 1800
        assert by_type["movie"]["title"] == "Movie Title"
        assert by_type["movie"]["description"] == "Movie description"
        assert by_type["movie"]["duration"] == 5400
        assert by_type["movie_extra"]["title"] == ""
        assert by_type["movie_extra"]["description"] is None
        assert by_type["movie_extra"]["duration"] == 0
        assert connection.execute(text(
            "SELECT media_item_id FROM media_downloads WHERE id = :id"
        ), {"id": download_id}).scalar_one() == extra_id

    engine.dispose()
