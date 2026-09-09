from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


PRE_SOURCE_REVISION = "d7c4a1f9b203"
SOURCE_REVISION = "f7c2a5d9e104"


def _insert_media_item(connection, *, uuid: str, media_type: str, title: str) -> int:
    return connection.execute(text(
        "INSERT INTO media_items "
        "(uuid, type, title, description, downloaded_date, duration, "
        "background_image_path, thumbnail_landscape_path, "
        "thumbnail_portrait_path, thumbnail_square_path) VALUES "
        "(:uuid, :type, :title, NULL, NULL, 60, NULL, NULL, NULL, NULL)"
    ), {
        "uuid": uuid,
        "type": media_type,
        "title": title,
    }).lastrowid


def test_source_migration_preserves_parent_placements_and_download_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Normalizing clip identity must not rewrite MediaItem or MediaDownload IDs."""
    from backend.db import core
    from backend.db.migrations import get_alembic_config

    database_path = tmp_path / "movie-extra-source-migration.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    command.upgrade(get_alembic_config(), PRE_SOURCE_REVISION)

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

        extra_a_id = _insert_media_item(
            connection,
            uuid="extra-a-uuid",
            media_type="movie_extra",
            title="Shared Teaser",
        )
        extra_b_id = _insert_media_item(
            connection,
            uuid="extra-b-uuid",
            media_type="movie_extra",
            title="Shared Teaser",
        )
        for extra_id, movie_id in (
            (extra_a_id, movie_a_id),
            (extra_b_id, movie_b_id),
        ):
            connection.execute(text(
                "INSERT INTO movie_extras "
                "(id, movie_id, movie_extra_type, slug, sharing_url, published_date, available_for) "
                "VALUES (:id, :movie_id, 'trailer', 'shared-teaser', NULL, NULL, '[]')"
            ), {
                "id": extra_id,
                "movie_id": movie_id,
            })
            connection.execute(text(
                "UPDATE movies SET official_trailer_id = :extra_id WHERE id = :movie_id"
            ), {
                "extra_id": extra_id,
                "movie_id": movie_id,
            })

        download_ids = []
        for extra_id, movie_name in (
            (extra_a_id, "Movie A"),
            (extra_b_id, "Movie B"),
        ):
            download_id = connection.execute(text(
                "INSERT INTO media_downloads "
                "(type, media_item_id, local_media_profile_id, file_path) "
                "VALUES ('movie_extra', :media_item_id, :profile_id, :file_path)"
            ), {
                "media_item_id": extra_id,
                "profile_id": profile_id,
                "file_path": f"/downloads/{movie_name}/shared-teaser.mp4",
            }).lastrowid
            connection.execute(
                text("INSERT INTO media_downloads_movie_extra (id) VALUES (:id)"),
                {"id": download_id},
            )
            download_ids.append(download_id)

    command.upgrade(get_alembic_config(), SOURCE_REVISION)

    with engine.connect() as connection:
        sources = connection.execute(text(
            "SELECT id, slug FROM movie_extra_sources"
        )).mappings().all()
        assert len(sources) == 1
        assert sources[0]["slug"] == "shared-teaser"

        placements = connection.execute(text(
            "SELECT id, movie_id, source_id FROM movie_extras ORDER BY id"
        )).mappings().all()
        assert [row["id"] for row in placements] == [extra_a_id, extra_b_id]
        assert len({row["source_id"] for row in placements}) == 1
        assert placements[0]["source_id"] == sources[0]["id"]

        official_trailers = connection.execute(text(
            "SELECT id, official_trailer_id FROM movies ORDER BY id"
        )).mappings().all()
        assert [row["official_trailer_id"] for row in official_trailers] == [
            extra_a_id,
            extra_b_id,
        ]

        downloads = connection.execute(text(
            "SELECT id, media_item_id, local_media_profile_id "
            "FROM media_downloads ORDER BY id"
        )).mappings().all()
        assert [row["id"] for row in downloads] == download_ids
        assert [row["media_item_id"] for row in downloads] == [extra_a_id, extra_b_id]
        assert {row["local_media_profile_id"] for row in downloads} == {profile_id}

    command.downgrade(get_alembic_config(), PRE_SOURCE_REVISION)

    inspector = inspect(engine)
    assert "movie_extra_sources" not in set(inspector.get_table_names())
    with engine.connect() as connection:
        restored = connection.execute(text(
            "SELECT id, slug FROM movie_extras ORDER BY id"
        )).mappings().all()
        assert [row["id"] for row in restored] == [extra_a_id, extra_b_id]
        assert {row["slug"] for row in restored} == {"shared-teaser"}
        assert connection.execute(text(
            "SELECT COUNT(*) FROM media_downloads"
        )).scalar_one() == 2
        assert [
            row["official_trailer_id"]
            for row in connection.execute(text(
                "SELECT official_trailer_id FROM movies ORDER BY id"
            )).mappings().all()
        ] == [extra_a_id, extra_b_id]

    engine.dispose()
