from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


HEAD_REVISION = "e5f1a2c7d903"
WIRELOFT_1_0_REVISION = "c8d4e2f1a7b9"
BASE_REVISION = "0001"


@pytest.fixture
def migration_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the shared DB layer at a disposable SQLite file."""
    from backend.db import core

    database_path = tmp_path / "wireloft-migration-test.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    yield database_path, engine
    engine.dispose()


def _upgrade_to_wireloft_1_0(engine) -> None:
    from backend.db.migrations import get_alembic_config

    command.upgrade(
        get_alembic_config(allow_version_storage_migration=True),
        WIRELOFT_1_0_REVISION,
    )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == WIRELOFT_1_0_REVISION


def _seed_wireloft_1_0_data(database_path: Path, engine) -> dict[str, int | str]:
    artifact_path = database_path.parent / "published-episode.mp4"
    artifact_path.write_bytes(b"wireloft-1.0-artifact")

    with engine.begin() as connection:
        profile_id = connection.execute(text(
            "SELECT id FROM local_media_profiles "
            "WHERE slug = 'wireloft-shows-video'"
        )).scalar_one()

        show_id = connection.execute(text(
            "INSERT INTO shows "
            "(uuid, slug, title, description, sharing_url, membership_level, type, "
            "episode_identifier, author_name, author_slug) VALUES "
            "('release-show-uuid', 'release-show', 'Release Show', 'Description', "
            "'https://example.test/release-show', 'FREE', 'series', 'seasonal', "
            "'Host', 'host')"
        )).lastrowid
        season_id = connection.execute(text(
            "INSERT INTO seasons (show_id, `index`, slug, name) "
            "VALUES (:show_id, 1, 'season-1', 'Season 1')"
        ), {"show_id": show_id}).lastrowid

        episode_id = connection.execute(text(
            "INSERT INTO media_items "
            "(uuid, type, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path) "
            "VALUES ('release-episode-uuid', 'episode', 'Release Episode', "
            "'Episode description', 1800, NULL, 'episode-land.jpg', NULL, NULL)"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO episodes "
            "(id, show_id, season_id, `index`, episode_identifier, slug, publish_status, "
            "video_url, audio_url, sharing_url, published_date, metadata_is_final) "
            "VALUES (:id, :show_id, :season_id, 1, 'ep.S01E01', 'release-episode', "
            "'published', 'https://video.test/master.m3u8', NULL, "
            "'https://example.test/release-episode', '2026-09-01 12:00:00', 1)"
        ), {
            "id": episode_id,
            "show_id": show_id,
            "season_id": season_id,
        })
        connection.execute(text(
            "INSERT INTO metadata (parent_table, parent_id, key, value) "
            "VALUES ('episodes', :episode_id, 'dw_processing.reason', 'release-test')"
        ), {"episode_id": episode_id})

        download_id = connection.execute(text(
            "INSERT INTO media_downloads "
            "(type, media_item_id, local_media_profile_id, download_status, file_path, "
            "progress, error_message, downloaded_bytes, format_downloaded, started_at, "
            "finished_at, attempt_generation) VALUES "
            "('episode', :episode_id, :profile_id, 'downloaded', :file_path, 100, NULL, "
            ":downloaded_bytes, '1920x1080', '2026-09-01 12:00:00', "
            "'2026-09-01 12:30:00', 1)"
        ), {
            "episode_id": episode_id,
            "profile_id": profile_id,
            "file_path": str(artifact_path),
            "downloaded_bytes": artifact_path.stat().st_size,
        }).lastrowid
        connection.execute(text(
            "INSERT INTO media_downloads_episode "
            "(id, download_profile_id, downloaded_publish_status, is_redownload_attempt) "
            "VALUES (:id, NULL, 'published', 0)"
        ), {"id": download_id})
        connection.execute(text(
            "INSERT INTO media_download_attempts "
            "(media_download_id, is_redownload, status, downloaded_bytes, "
            "format_downloaded, started_at, finished_at) VALUES "
            "(:download_id, 0, 'downloaded', :downloaded_bytes, '1920x1080', "
            "'2026-09-01 12:00:00', '2026-09-01 12:30:00')"
        ), {
            "download_id": download_id,
            "downloaded_bytes": artifact_path.stat().st_size,
        })

        task_definition_id = connection.execute(text(
            "INSERT INTO task_definitions "
            "(key, title, description, allowed_resource_types, default_max_retries) "
            "VALUES ('monitor_episode_worker', 'Legacy monitor', NULL, '[\"episode\"]', 3)"
        )).lastrowid

        movie_id = connection.execute(text(
            "INSERT INTO media_items "
            "(uuid, type, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path) "
            "VALUES ('release-movie-uuid', 'movie', 'Release Movie', 'Movie description', "
            "5400, NULL, 'movie-land.jpg', 'movie-port.jpg', 'movie-square.jpg')"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO movies "
            "(id, slug, dw_id, sharing_url, is_downloadable, available_for, "
            "release_date_lookup_status) VALUES "
            "(:id, 'release-movie', 'rotating-movie-id', "
            "'https://example.test/release-movie', 1, '[\"ALL_ACCESS\"]', 'pending')"
        ), {"id": movie_id})

        movie_extra_id = connection.execute(text(
            "INSERT INTO media_items "
            "(uuid, type, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path) "
            "VALUES ('release-extra-uuid', 'movie_extra', 'Official Trailer', "
            "'Trailer description', 120, NULL, 'trailer-land.jpg', NULL, NULL)"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO movie_extras "
            "(id, movie_id, movie_extra_type, dw_id, slug, sharing_url, published_date) "
            "VALUES (:id, :movie_id, 'trailer', 'rotating-extra-id', "
            "'release-movie-trailer', 'https://example.test/trailer', "
            "'2026-08-01 12:00:00')"
        ), {"id": movie_extra_id, "movie_id": movie_id})
        connection.execute(text(
            "UPDATE movies SET official_trailer_id = :extra_id WHERE id = :movie_id"
        ), {"extra_id": movie_extra_id, "movie_id": movie_id})

    return {
        "profile_id": int(profile_id),
        "show_id": int(show_id),
        "episode_id": int(episode_id),
        "download_id": int(download_id),
        "task_definition_id": int(task_definition_id),
        "movie_id": int(movie_id),
        "movie_extra_id": int(movie_extra_id),
        "artifact_path": str(artifact_path),
    }


def test_migration_history_has_one_head(migration_database):
    _database_path, _engine = migration_database
    from backend.db.migrations import get_alembic_config

    script = ScriptDirectory.from_config(
        get_alembic_config(allow_version_storage_migration=True)
    )

    assert script.get_heads() == [HEAD_REVISION]
    assert script.get_revision(HEAD_REVISION) is not None
    assert script.get_revision(BASE_REVISION) is not None


def test_fresh_database_upgrades_to_wireloft_1_1(migration_database):
    database_path, engine = migration_database
    from backend.db.migrations import get_database_status, upgrade_database

    assert not database_path.exists()
    upgrade_database()

    current, head = get_database_status()
    assert current == (HEAD_REVISION,)
    assert head == HEAD_REVISION

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "task_operations" in tables
    assert "movie_extra_sources" in tables
    assert "media_download_attempts" not in tables
    assert "alembic_version" not in tables

    settings_columns = {
        column["name"] for column in inspector.get_columns("settings")
    }
    assert "background_migration_version" in settings_columns

    profile_columns = {
        column["name"] for column in inspector.get_columns("local_media_profiles")
    }
    assert "download_mode" in profile_columns
    profile_indexes = {index["name"] for index in inspector.get_indexes("local_media_profiles")}
    assert "uq_local_media_profiles_type_output_template_preferred_format" in profile_indexes
    assert "uq_local_media_profiles_type_template_format_mode" not in profile_indexes

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT alembic_version_num FROM settings"
        )).scalar_one() == HEAD_REVISION


def test_upgrade_from_wireloft_1_0_preserves_release_data(migration_database):
    database_path, engine = migration_database
    from backend.db.migrations import upgrade_database

    _upgrade_to_wireloft_1_0(engine)
    seeded = _seed_wireloft_1_0_data(database_path, engine)
    upgrade_database()

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "media_download_attempts" not in tables
    assert "task_operations" in tables
    assert "alembic_version" not in tables

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT alembic_version_num FROM settings"
        )).scalar_one() == HEAD_REVISION

        episode = connection.execute(text(
            "SELECT slug, title, metadata_is_final "
            "FROM media_items_episode WHERE id = :id"
        ), {"id": seeded["episode_id"]}).mappings().one()
        assert episode["slug"] == "release-episode"
        assert episode["title"] == "Release Episode"
        assert bool(episode["metadata_is_final"])

        metadata = connection.execute(text(
            "SELECT parent_table, key, value FROM metadata WHERE parent_id = :id"
        ), {"id": seeded["episode_id"]}).mappings().one()
        assert metadata["parent_table"] == "media_items_episode"
        assert metadata["key"] == "no_usable_media.reason"
        assert metadata["value"] == "release-test"

        download = connection.execute(text(
            "SELECT artifact_status, artifact_error, artifact_size_bytes, "
            "artifact_fingerprint, downloaded_bytes, format_downloaded, file_path "
            "FROM media_downloads WHERE id = :id"
        ), {"id": seeded["download_id"]}).mappings().one()
        assert download["artifact_status"] == "available"
        assert download["artifact_error"] is None
        assert download["artifact_size_bytes"] == Path(str(seeded["artifact_path"])).stat().st_size
        assert len(download["artifact_fingerprint"]) == 64
        assert download["downloaded_bytes"] == Path(str(seeded["artifact_path"])).stat().st_size
        assert download["format_downloaded"] == "1920x1080"
        assert download["file_path"] == seeded["artifact_path"]

        assert connection.execute(text(
            "SELECT key FROM task_definitions WHERE id = :id"
        ), {"id": seeded["task_definition_id"]}).scalar_one() == "monitor_pending_episode"

        movie = connection.execute(text(
            "SELECT slug, title, is_downloadable, official_trailer_id "
            "FROM media_items_movie WHERE id = :id"
        ), {"id": seeded["movie_id"]}).mappings().one()
        assert movie["slug"] == "release-movie"
        assert movie["title"] == "Release Movie"
        assert bool(movie["is_downloadable"])
        assert movie["official_trailer_id"] == seeded["movie_extra_id"]

        extra = connection.execute(text(
            "SELECT placement.movie_extra_type, source.slug, source.title "
            "FROM media_items_movie_extra AS placement "
            "JOIN movie_extra_sources AS source ON source.id = placement.source_id "
            "WHERE placement.id = :id"
        ), {"id": seeded["movie_extra_id"]}).mappings().one()
        assert extra["movie_extra_type"] == "trailer"
        assert extra["slug"] == "release-movie-trailer"
        assert extra["title"] == "Official Trailer"

        profile = connection.execute(text(
            "SELECT download_mode FROM local_media_profiles WHERE id = :id"
        ), {"id": seeded["profile_id"]}).scalar_one()
        assert profile == "system"
        assert connection.execute(text(
            "SELECT show_scope FROM local_media_profiles_show WHERE id = :id"
        ), {"id": seeded["profile_id"]}).scalar_one() == "both"


def test_wireloft_1_1_downgrades_to_1_0_schema(migration_database):
    database_path, engine = migration_database
    from backend.db.migrations import downgrade_database, upgrade_database

    _upgrade_to_wireloft_1_0(engine)
    seeded = _seed_wireloft_1_0_data(database_path, engine)
    upgrade_database()
    downgrade_database(WIRELOFT_1_0_REVISION)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "task_operations" not in tables
    assert "media_download_attempts" in tables
    assert "episodes" in tables
    assert "movies" in tables
    assert "movie_extras" in tables
    assert "media_items_episode" not in tables

    assert "download_mode" not in {
        column["name"] for column in inspector.get_columns("local_media_profiles")
    }
    assert "timezone" in {
        column["name"] for column in inspector.get_columns("task_schedules")
    }
    assert "is_no_show_today" in {
        column["name"] for column in inspector.get_columns("episodes")
    }
    assert "artifact_status" not in {
        column["name"] for column in inspector.get_columns("media_downloads")
    }
    assert "download_status" in {
        column["name"] for column in inspector.get_columns("media_downloads")
    }
    assert "background_migration_version" not in {
        column["name"] for column in inspector.get_columns("settings")
    }

    with engine.connect() as connection:
        # The old attempt table is structurally restored, but its 1.0 history was
        # intentionally discarded during the upgrade.
        assert connection.execute(text(
            "SELECT COUNT(*) FROM media_download_attempts"
        )).scalar_one() == 0
        assert connection.execute(text(
            "SELECT slug FROM episodes WHERE id = :id"
        ), {"id": seeded["episode_id"]}).scalar_one() == "release-episode"
        assert connection.execute(text(
            "SELECT slug FROM movies WHERE id = :id"
        ), {"id": seeded["movie_id"]}).scalar_one() == "release-movie"
        assert connection.execute(text(
            "SELECT slug FROM movie_extras WHERE id = :id"
        ), {"id": seeded["movie_extra_id"]}).scalar_one() == "release-movie-trailer"
        assert connection.execute(text(
            "SELECT key FROM task_definitions WHERE id = :id"
        ), {"id": seeded["task_definition_id"]}).scalar_one() == "monitor_episode_worker"
        assert connection.execute(text(
            "SELECT alembic_version_num FROM settings"
        )).scalar_one() == WIRELOFT_1_0_REVISION
