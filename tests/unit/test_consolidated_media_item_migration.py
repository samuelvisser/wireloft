from __future__ import annotations

import json
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


PRE_CONSOLIDATION_REVISION = "c9f2d8a1b604"
CONSOLIDATED_REVISION = "c5a9e2f7b104"

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
    description: str | None = None,
    duration: float = 0,
    prefix: str | None = None,
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


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    return json.loads(value) if value else []


def test_consolidated_migration_upgrades_directly_from_c9_and_downgrades_cleanly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.db import core
    from backend.db.migrations import get_alembic_config

    database_path = tmp_path / "consolidated-media-items.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    command.upgrade(get_alembic_config(), PRE_CONSOLIDATION_REVISION)

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
        connection.execute(text(
            "INSERT INTO metadata (parent_table, parent_id, key, value) "
            "VALUES ('episodes', :episode_id, 'migration.test', 'preserved')"
        ), {"episode_id": episode_id})

        movie_a_id = _insert_media_item(
            connection,
            uuid="movie-a-uuid",
            media_type="movie",
            title="Movie A",
            description="Movie A description",
            duration=5400,
            prefix="movie-a",
        )
        movie_b_id = _insert_media_item(
            connection,
            uuid="movie-b-uuid",
            media_type="movie",
            title="Movie B",
            description="Movie B description",
            duration=5600,
            prefix="movie-b",
        )
        for movie_id, dw_id, slug in (
            (movie_a_id, "movie-a-dw-id", "movie-a"),
            (movie_b_id, "movie-b-dw-id", "movie-b"),
        ):
            connection.execute(text(
                "INSERT INTO movies "
                "(id, dw_id, slug, release_date_source, release_date_source_id, "
                "more_like_this, shop_items, production_companies) VALUES "
                "(:id, :dw_id, :slug, 'dailywire', :dw_id, "
                "'[{\"slug\":\"promoted\"}]', '[{\"sku\":\"shirt\"}]', '[\"studio\"]')"
            ), {
                "id": movie_id,
                "dw_id": dw_id,
                "slug": slug,
            })

        extra_a_id = _insert_media_item(
            connection,
            uuid="extra-a-uuid",
            media_type="movie_extra",
            title="Shared Extra",
            description="Canonical extra description",
            duration=95,
            prefix="extra",
        )
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
            "(id, movie_id, dw_id, slug, movie_extra_type, sharing_url, "
            "published_date, available_for) VALUES "
            "(:id, :movie_id, 'extra-a-dw-id', 'shared-extra', 'trailer', "
            "'https://www.dailywire.com/videos/shared-extra', "
            "'2026-09-01 12:30:00+00:00', '[\"ALL_ACCESS\"]')"
        ), {
            "id": extra_a_id,
            "movie_id": movie_a_id,
        })
        connection.execute(text(
            "INSERT INTO movie_extras "
            "(id, movie_id, dw_id, slug, movie_extra_type, sharing_url, "
            "published_date, available_for) VALUES "
            "(:id, :movie_id, 'extra-b-dw-id', 'shared-extra', 'scene', "
            "NULL, NULL, '[]')"
        ), {
            "id": extra_b_id,
            "movie_id": movie_b_id,
        })
        for movie_id, extra_id in (
            (movie_a_id, extra_a_id),
            (movie_b_id, extra_b_id),
        ):
            connection.execute(text(
                "UPDATE movies SET official_trailer_id = :extra_id WHERE id = :movie_id"
            ), {
                "movie_id": movie_id,
                "extra_id": extra_id,
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
        download_ids = []
        for extra_id, suffix in ((extra_a_id, "a"), (extra_b_id, "b")):
            download_id = connection.execute(text(
                "INSERT INTO media_downloads "
                "(type, media_item_id, local_media_profile_id, file_path) "
                "VALUES ('movie_extra', :extra_id, :profile_id, :path)"
            ), {
                "extra_id": extra_id,
                "profile_id": profile_id,
                "path": f"/downloads/shared-extra-{suffix}.mp4",
            }).lastrowid
            connection.execute(
                text("INSERT INTO media_downloads_movie_extra (id) VALUES (:id)"),
                {"id": download_id},
            )
            download_ids.append(download_id)

    command.upgrade(get_alembic_config(), CONSOLIDATED_REVISION)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "media_items_episodes",
        "media_items_movies",
        "media_items_movie_extras",
        "movie_extra_sources",
    } <= tables
    assert {"episodes", "movies", "movie_extras"}.isdisjoint(tables)
    assert _CONTENT_FIELDS.isdisjoint(
        {column["name"] for column in inspector.get_columns("media_items")}
    )
    assert _CONTENT_FIELDS <= {
        column["name"] for column in inspector.get_columns("media_items_episodes")
    }
    movie_columns = {
        column["name"] for column in inspector.get_columns("media_items_movies")
    }
    assert _CONTENT_FIELDS <= movie_columns
    assert {"dw_id", "more_like_this", "shop_items"}.isdisjoint(movie_columns)
    assert {
        column["name"]
        for column in inspector.get_columns("media_items_movie_extras")
    } == {"id", "movie_id", "source_id", "movie_extra_type"}

    with engine.connect() as connection:
        episode = connection.execute(text(
            "SELECT title, description, duration FROM media_items_episodes WHERE id = :id"
        ), {"id": episode_id}).mappings().one()
        assert dict(episode) == {
            "title": "Episode Title",
            "description": "Episode description",
            "duration": 1800,
        }
        assert connection.execute(text(
            "SELECT parent_table FROM metadata WHERE parent_id = :id AND key = 'migration.test'"
        ), {"id": episode_id}).scalar_one() == "media_items_episodes"

        movies = connection.execute(text(
            "SELECT id, title, release_date_source_id, official_trailer_id "
            "FROM media_items_movies ORDER BY id"
        )).mappings().all()
        assert [row["title"] for row in movies] == ["Movie A", "Movie B"]
        assert [row["release_date_source_id"] for row in movies] == [None, None]
        assert [row["official_trailer_id"] for row in movies] == [extra_a_id, extra_b_id]

        sources = connection.execute(text(
            "SELECT id, slug, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path, "
            "sharing_url, published_date, available_for FROM movie_extra_sources"
        )).mappings().all()
        assert len(sources) == 1
        source = sources[0]
        assert source["slug"] == "shared-extra"
        assert source["title"] == "Shared Extra"
        assert source["description"] == "Canonical extra description"
        assert source["duration"] == 95
        assert source["background_image_path"] == "extra-background.jpg"
        assert source["thumbnail_landscape_path"] == "extra-landscape.jpg"
        assert source["thumbnail_portrait_path"] == "extra-portrait.jpg"
        assert source["thumbnail_square_path"] == "extra-square.jpg"
        assert source["sharing_url"] == "https://www.dailywire.com/videos/shared-extra"
        assert source["published_date"] is not None
        assert _json_list(source["available_for"]) == ["ALL_ACCESS"]

        placements = connection.execute(text(
            "SELECT id, movie_id, source_id, movie_extra_type "
            "FROM media_items_movie_extras ORDER BY id"
        )).mappings().all()
        assert [row["id"] for row in placements] == [extra_a_id, extra_b_id]
        assert len({row["source_id"] for row in placements}) == 1
        assert {row["movie_extra_type"] for row in placements} == {"trailer", "scene"}

        downloads = connection.execute(text(
            "SELECT id, media_item_id FROM media_downloads ORDER BY id"
        )).mappings().all()
        assert [row["id"] for row in downloads] == download_ids
        assert [row["media_item_id"] for row in downloads] == [extra_a_id, extra_b_id]

    command.downgrade(get_alembic_config(), PRE_CONSOLIDATION_REVISION)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"episodes", "movies", "movie_extras"} <= tables
    assert {
        "media_items_episodes",
        "media_items_movies",
        "media_items_movie_extras",
        "movie_extra_sources",
    }.isdisjoint(tables)
    assert _CONTENT_FIELDS <= {
        column["name"] for column in inspector.get_columns("media_items")
    }
    assert _CONTENT_FIELDS.isdisjoint(
        {column["name"] for column in inspector.get_columns("episodes")}
    )
    assert _CONTENT_FIELDS.isdisjoint(
        {column["name"] for column in inspector.get_columns("movies")}
    )
    assert {"dw_id", "more_like_this", "shop_items"} <= {
        column["name"] for column in inspector.get_columns("movies")
    }

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT parent_table FROM metadata WHERE parent_id = :id AND key = 'migration.test'"
        ), {"id": episode_id}).scalar_one() == "episodes"

        restored_media = connection.execute(text(
            "SELECT id, type, title, description, duration FROM media_items "
            "WHERE id IN (:episode, :movie_a, :movie_b, :extra_a, :extra_b) ORDER BY id"
        ), {
            "episode": episode_id,
            "movie_a": movie_a_id,
            "movie_b": movie_b_id,
            "extra_a": extra_a_id,
            "extra_b": extra_b_id,
        }).mappings().all()
        by_id = {row["id"]: row for row in restored_media}
        assert by_id[episode_id]["title"] == "Episode Title"
        assert by_id[movie_a_id]["title"] == "Movie A"
        assert by_id[movie_b_id]["title"] == "Movie B"
        assert by_id[extra_a_id]["title"] == "Shared Extra"
        assert by_id[extra_b_id]["title"] == "Shared Extra"
        assert by_id[extra_a_id]["description"] == "Canonical extra description"
        assert by_id[extra_b_id]["description"] == "Canonical extra description"

        restored_extras = connection.execute(text(
            "SELECT id, dw_id, slug, sharing_url, available_for "
            "FROM movie_extras ORDER BY id"
        )).mappings().all()
        assert [row["id"] for row in restored_extras] == [extra_a_id, extra_b_id]
        assert [row["dw_id"] for row in restored_extras] == [None, None]
        assert {row["slug"] for row in restored_extras} == {"shared-extra"}
        assert all(
            row["sharing_url"] == "https://www.dailywire.com/videos/shared-extra"
            for row in restored_extras
        )
        assert all(_json_list(row["available_for"]) == ["ALL_ACCESS"] for row in restored_extras)

        restored_movies = connection.execute(text(
            "SELECT id, dw_id, official_trailer_id, more_like_this, shop_items "
            "FROM movies ORDER BY id"
        )).mappings().all()
        assert [row["dw_id"] for row in restored_movies] == [None, None]
        assert [row["official_trailer_id"] for row in restored_movies] == [
            extra_a_id,
            extra_b_id,
        ]
        assert all(_json_list(row["more_like_this"]) == [] for row in restored_movies)
        assert all(_json_list(row["shop_items"]) == [] for row in restored_movies)
        assert connection.execute(text(
            "SELECT COUNT(*) FROM media_downloads"
        )).scalar_one() == 2

    engine.dispose()
