from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


HEAD_REVISION = "6d3a9f1c2b7e"
WIRELOFT_1_2_1_REVISION = "f2a6c93d8b14"
WIRELOFT_1_2_REVISION = "6d4a8c1f2b90"
PRE_HISTORY_HEAD_REVISION = "6d1e8f2a4c73"
PRE_HISTORY_PARENT_REVISION = "d4a7c2e91b63"
PREVIOUS_DEVELOPMENT_REVISION = "e5f1a2c7d903"
HISTORICAL_EPISODE_SCHEMA_REVISION = "e4c91a7b2d30"
OUTPUT_TEMPLATE_SPACING_REVISION = "9b1f4e7c2d6a"
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
        )).scalar_one_or_none()
        if profile_id is None:
            profile_id = connection.execute(text(
                "INSERT INTO local_media_profiles "
                "(type, slug, name, output_template, preferred_format, "
                "append_media_type_to_filename) VALUES "
                "('show', 'wireloft-shows-video', 'WireLoft Shows (Video)', "
                "'/downloads/shows/{{ show_title }}/{{ season_name }}/{{ episode_title }}.ext', "
                "'format_1080p', 0)"
            )).lastrowid
            connection.execute(text(
                "INSERT INTO local_media_profiles_show (id) VALUES (:profile_id)"
            ), {"profile_id": profile_id})

        show_id = connection.execute(text(
            "INSERT INTO shows "
            "(uuid, slug, title, description, sharing_url, membership_level, type, "
            "episode_identifier, author_name, author_slug) VALUES "
            "('release-show-uuid', 'release-show', 'Release Show', 'Description', "
            "'https://www.dailywire.com/show/release-show', 'FREE', 'series', 'seasonal', "
            "'Host', 'host')"
        )).lastrowid
        extra_season_id = connection.execute(text(
            "INSERT INTO seasons (show_id, `index`, slug, name) "
            "VALUES (:show_id, 1, 'extras', 'Extras')"
        ), {"show_id": show_id}).lastrowid
        season_id = connection.execute(text(
            "INSERT INTO seasons (show_id, `index`, slug, name) "
            "VALUES (:show_id, 2, 'season-1', 'Season 1')"
        ), {"show_id": show_id}).lastrowid
        for key, value in (
            ("ep_id.latest_ep_num", "1"),
            ("ep_id.latest_ep_extra_num", "1"),
            ("ep_id.latest_season_2_ep", "1"),
        ):
            connection.execute(
                text(
                    "INSERT INTO metadata (parent_table, parent_id, key, value) "
                    "VALUES ('shows', :show_id, :key, :value)"
                ),
                {"show_id": show_id, "key": key, "value": value},
            )

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
            "VALUES (:id, :show_id, :season_id, 1, 'ep.S02E01', 'release-episode', "
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

        trailer_episode_id = connection.execute(text(
            "INSERT INTO media_items "
            "(uuid, type, title, description, duration, background_image_path, "
            "thumbnail_landscape_path, thumbnail_portrait_path, thumbnail_square_path) "
            "VALUES ('release-trailer-episode-uuid', 'episode', "
            "'Release Show | Official Trailer', 'Trailer description', 90, NULL, "
            "'trailer-episode-land.jpg', NULL, NULL)"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO episodes "
            "(id, show_id, season_id, `index`, episode_identifier, slug, publish_status, "
            "video_url, audio_url, sharing_url, published_date, metadata_is_final) "
            "VALUES (:id, :show_id, :season_id, 2, 'aux.1', 'release-show-trailer', "
            "'published', 'https://video.test/trailer.m3u8', NULL, "
            "'https://example.test/release-show-trailer', "
            "'2026-08-31 12:00:00', 1)"
        ), {
            "id": trailer_episode_id,
            "show_id": show_id,
            "season_id": extra_season_id,
        })

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
        "extra_season_id": int(extra_season_id),
        "season_id": int(season_id),
        "episode_id": int(episode_id),
        "trailer_episode_id": int(trailer_episode_id),
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
    assert script.get_revision(HEAD_REVISION).down_revision == WIRELOFT_1_2_1_REVISION
    assert script.get_revision(WIRELOFT_1_2_1_REVISION).down_revision == WIRELOFT_1_2_REVISION
    assert (
        script.get_revision(WIRELOFT_1_2_REVISION).down_revision
        == "d8b4a1f6c203"
    )
    assert script.get_revision("d8b4a1f6c203").down_revision == WIRELOFT_1_0_REVISION
    assert script.get_revision(WIRELOFT_1_0_REVISION).down_revision == BASE_REVISION
    assert script.get_revision(BASE_REVISION) is not None



def test_countdown_redownload_intent_migration_uses_current_episode_table(migration_database):
    _database_path, engine = migration_database
    from backend.db.migrations import get_alembic_config, upgrade_database

    command.upgrade(
        get_alembic_config(allow_version_storage_migration=True),
        WIRELOFT_1_2_1_REVISION,
    )

    with engine.begin() as connection:
        show_id = connection.execute(text(
            "INSERT INTO shows "
            "(uuid, slug, title, description, sharing_url, membership_level, type, "
            "episode_identifier, author_name, author_slug) VALUES "
            "('countdown-migration-show', 'countdown-migration-show', 'Countdown Migration', "
            "NULL, 'https://example.test/countdown-migration-show', 'FREE', 'podcast', "
            "'numbered', 'Host', 'host')"
        )).lastrowid
        season_id = connection.execute(text(
            "INSERT INTO seasons (show_id, `index`, slug, name) "
            "VALUES (:show_id, 1, 'season-1', 'Season 1')"
        ), {"show_id": show_id}).lastrowid
        media_item_id = connection.execute(text(
            "INSERT INTO media_items (uuid, type) "
            "VALUES ('countdown-migration-episode', 'episode')"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO media_items_episode "
            "(id, show_id, season_id, `index`, episode_identifier, slug, publish_status, "
            "sharing_url, title, duration, metadata_is_final) VALUES "
            "(:id, :show_id, :season_id, 1, 'ep.1', 'countdown-migration-episode', "
            "'published_with_countdown', 'https://example.test/countdown-migration-episode', "
            "'Countdown Episode', 1800, 1)"
        ), {
            "id": media_item_id,
            "show_id": show_id,
            "season_id": season_id,
        })

        local_profile_id = connection.execute(text(
            "INSERT INTO local_media_profiles "
            "(slug, name, output_template, preferred_format, type) VALUES "
            "('countdown-migration-audio', 'Countdown Migration Audio', "
            "'/downloads/{{ episode_title }}.ext', 'format_audio_only', 'show')"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO local_media_profiles_show (id) VALUES (:id)"
        ), {"id": local_profile_id})

        download_profile_id = connection.execute(text(
            "INSERT INTO download_profiles "
            "(show_id, local_media_profile_id, type, enable_profile, ep_id_type_list) "
            "VALUES (:show_id, :local_profile_id, 'podcast', 1, '[\"ep\"]')"
        ), {
            "show_id": show_id,
            "local_profile_id": local_profile_id,
        }).lastrowid
        connection.execute(text(
            "INSERT INTO download_profiles_podcast "
            "(id, download_with_countdown, redownload_final, download_days_in_past, "
            "delete_older_episodes, download_episode_count) "
            "VALUES (:id, 1, 1, 0, 0, 0)"
        ), {"id": download_profile_id})

        media_download_id = connection.execute(text(
            "INSERT INTO media_downloads "
            "(type, media_item_id, local_media_profile_id, file_path, artifact_status) "
            "VALUES ('episode', :media_item_id, :local_profile_id, "
            "'/downloads/countdown.m4a', 'available')"
        ), {
            "media_item_id": media_item_id,
            "local_profile_id": local_profile_id,
        }).lastrowid
        connection.execute(text(
            "INSERT INTO media_downloads_episode "
            "(id, download_profile_id, downloaded_publish_status) "
            "VALUES (:id, :download_profile_id, 'published_with_countdown')"
        ), {
            "id": media_download_id,
            "download_profile_id": download_profile_id,
        })

    upgrade_database()

    inspector = inspect(engine)
    assert "redownload_when_final" in {
        column["name"]
        for column in inspector.get_columns("media_downloads_episode")
    }
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT redownload_when_final FROM media_downloads_episode WHERE id = :id"
        ), {"id": media_download_id}).scalar_one() == 1
        assert connection.execute(text(
            "SELECT alembic_version_num FROM settings"
        )).scalar_one() == HEAD_REVISION


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
    assert "custom_index_states" in tables
    assert {"requested_generation", "completed_generation"} <= {
        column["name"] for column in inspector.get_columns("custom_index_states")
    }
    assert "media_download_attempts" not in tables
    assert "media_download_history" in tables
    assert "alembic_version" not in tables

    settings_columns = {
        column["name"] for column in inspector.get_columns("settings")
    }
    assert "background_migration_version" in settings_columns

    media_download_columns = {
        column["name"] for column in inspector.get_columns("media_downloads")
    }
    assert "first_successful_download_at" not in media_download_columns

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
        assert connection.execute(text(
            "SELECT onboarding_completed FROM settings"
        )).scalar_one() == 0

        profiles = connection.execute(text(
            "SELECT type, slug, output_template, preferred_format "
            "FROM local_media_profiles ORDER BY slug"
        )).mappings().all()
        assert [profile["slug"] for profile in profiles] == [
            "wireloft-movies",
            "wireloft-shows-audio",
            "wireloft-shows-video",
        ]
        assert {profile["type"] for profile in profiles} == {"movie", "show"}
        assert connection.execute(text(
            "SELECT COUNT(*) FROM local_media_profiles_show"
        )).scalar_one() == 2
        assert connection.execute(text(
            "SELECT COUNT(*) FROM local_media_profiles_movie"
        )).scalar_one() == 1

    from backend.db.initial_seed import seed_initial_database

    seed_initial_database()
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM local_media_profiles"
        )).scalar_one() == 3


def test_existing_database_upgrade_does_not_run_initial_seed(migration_database):
    _database_path, engine = migration_database
    from backend.db.migrations import upgrade_database

    _upgrade_to_wireloft_1_0(engine)
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM local_media_profiles"
        )).scalar_one() == 0

    upgrade_database()

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM local_media_profiles"
        )).scalar_one() == 0


def test_historical_e4_production_database_upgrades_to_current_head(migration_database):
    _database_path, engine = migration_database
    from backend.db.migrations import (
        get_alembic_config,
        get_database_status,
        upgrade_database,
    )

    command.upgrade(
        get_alembic_config(allow_version_storage_migration=True),
        HISTORICAL_EPISODE_SCHEMA_REVISION,
    )

    inspector = inspect(engine)
    settings_columns = {
        column["name"] for column in inspector.get_columns("settings")
    }
    season_columns = {
        column["name"] for column in inspector.get_columns("seasons")
    }
    episode_columns = {
        column["name"] for column in inspector.get_columns("media_items_episode")
    }

    # This matches the production state that exposed the missing historical
    # revision: e4 is current, its episode-indexing columns exist, and e5 has not
    # yet introduced background_migration_version.
    assert "background_migration_version" not in settings_columns
    assert {"season_type", "season_number"} <= season_columns
    assert "dw_episode_number" in episode_columns
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT alembic_version_num FROM settings"
        )).scalar_one() == HISTORICAL_EPISODE_SCHEMA_REVISION

    upgrade_database()

    current, head = get_database_status()
    assert current == (HEAD_REVISION,)
    assert head == HEAD_REVISION

    inspector = inspect(engine)
    assert "background_migration_version" in {
        column["name"] for column in inspector.get_columns("settings")
    }
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT alembic_version_num FROM settings"
        )).scalar_one() == HEAD_REVISION


def test_episode_indexing_migration_upgrades_from_previous_development_head(migration_database):
    _database_path, engine = migration_database
    from backend.db.migrations import get_alembic_config, get_database_status, upgrade_database

    command.upgrade(
        get_alembic_config(allow_version_storage_migration=True),
        PREVIOUS_DEVELOPMENT_REVISION,
    )

    # The media database refactor has already moved content metadata onto the
    # concrete episode table by this revision. The episode-indexing migration
    # must therefore read title from media_items_episode, not media_items.
    inspector = inspect(engine)
    assert "title" not in {
        column["name"] for column in inspector.get_columns("media_items")
    }
    assert "title" in {
        column["name"] for column in inspector.get_columns("media_items_episode")
    }

    upgrade_database()

    current, head = get_database_status()
    assert current == (HEAD_REVISION,)
    assert head == HEAD_REVISION


def test_episode_indexing_migration_resumes_after_interrupted_column_adds(migration_database):
    _database_path, engine = migration_database
    from backend.db.migrations import get_alembic_config, get_database_status, upgrade_database

    command.upgrade(
        get_alembic_config(allow_version_storage_migration=True),
        OUTPUT_TEMPLATE_SPACING_REVISION,
    )

    # SQLite can retain these additive DDL changes when a later statement in the
    # revision fails. Reproduce that state while leaving Alembic before e4c91a7b2d30.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE seasons ADD COLUMN season_type VARCHAR DEFAULT 'normal' NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE seasons ADD COLUMN season_number INTEGER DEFAULT 1 NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE media_items_episode ADD COLUMN dw_episode_number VARCHAR"
        )

    current, _head = get_database_status()
    assert current == (OUTPUT_TEMPLATE_SPACING_REVISION,)

    upgrade_database()

    current, head = get_database_status()
    assert current == (HEAD_REVISION,)
    assert head == HEAD_REVISION

    inspector = inspect(engine)
    season_columns = [column["name"] for column in inspector.get_columns("seasons")]
    episode_columns = [
        column["name"] for column in inspector.get_columns("media_items_episode")
    ]
    assert season_columns.count("season_type") == 1
    assert season_columns.count("season_number") == 1
    assert episode_columns.count("dw_episode_number") == 1


def test_episode_indexing_migration_normalizes_background_revision(migration_database):
    _database_path, engine = migration_database
    from backend.db.migrations import (
        downgrade_database,
        get_alembic_config,
        upgrade_database,
    )

    command.upgrade(
        get_alembic_config(allow_version_storage_migration=True),
        PREVIOUS_DEVELOPMENT_REVISION,
    )
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE settings SET background_migration_version = "
            "'episode_indexing_semantics'"
        ))

    upgrade_database()

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT background_migration_version FROM settings"
        )).scalar_one() == "f6a1c3d8b427"

    downgrade_database(PREVIOUS_DEVELOPMENT_REVISION)

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT background_migration_version FROM settings"
        )).scalar_one() is None


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
            "SELECT slug, title, metadata_is_final, dw_episode_number, episode_identifier "
            "FROM media_items_episode WHERE id = :id"
        ), {"id": seeded["episode_id"]}).mappings().one()
        assert episode["slug"] == "release-episode"
        assert episode["title"] == "Release Episode"
        assert bool(episode["metadata_is_final"])
        assert episode["dw_episode_number"] is None
        assert episode["episode_identifier"] == "ep.S01E01"

        trailer_episode = connection.execute(text(
            "SELECT title, episode_identifier FROM media_items_episode WHERE id = :id"
        ), {"id": seeded["trailer_episode_id"]}).mappings().one()
        assert trailer_episode["title"] == "Release Show | Official Trailer"
        assert trailer_episode["episode_identifier"] == "trailer.1"

        extra_season = connection.execute(text(
            "SELECT season_type, season_number FROM seasons WHERE id = :id"
        ), {"id": seeded["extra_season_id"]}).mappings().one()
        assert extra_season["season_type"] == "extra"
        assert extra_season["season_number"] == 0

        season = connection.execute(text(
            "SELECT season_type, season_number FROM seasons WHERE id = :id"
        ), {"id": seeded["season_id"]}).mappings().one()
        assert season["season_type"] == "normal"
        assert season["season_number"] == 1

        retired_counters = connection.execute(
            text(
                "SELECT key FROM metadata "
                "WHERE parent_table = 'shows' AND parent_id = :show_id "
                "AND (key = 'ep_id.latest_ep_num' "
                "OR key = 'ep_id.latest_ep_extra_num' "
                "OR key LIKE 'ep_id.latest_season_%_ep')"
            ),
            {"show_id": seeded["show_id"]},
        ).scalars().all()
        assert retired_counters == []

        assert connection.execute(text(
            "SELECT background_migration_version FROM settings"
        )).scalar_one() is None

        metadata = connection.execute(text(
            "SELECT parent_table, key, value FROM metadata "
            "WHERE parent_table = 'media_items_episode' AND parent_id = :id"
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
    assert "dw_episode_number" not in {
        column["name"] for column in inspector.get_columns("episodes")
    }
    assert "season_type" not in {
        column["name"] for column in inspector.get_columns("seasons")
    }
    assert "season_number" not in {
        column["name"] for column in inspector.get_columns("seasons")
    }

    with engine.connect() as connection:
        # The old attempt table is structurally restored, but its 1.0 history was
        # intentionally discarded during the upgrade.
        assert connection.execute(text(
            "SELECT COUNT(*) FROM media_download_attempts"
        )).scalar_one() == 0
        downgraded_episode = connection.execute(
            text("SELECT slug, episode_identifier FROM episodes WHERE id = :id"),
            {"id": seeded["episode_id"]},
        ).mappings().one()
        assert downgraded_episode["slug"] == "release-episode"
        assert downgraded_episode["episode_identifier"] == "ep.S02E01"
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
