from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


HEAD_REVISION = "d4f0a9c2e713"
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


def test_fresh_database_upgrades_to_head(migration_database):
    database_path, engine = migration_database

    from backend.db.migrations import get_database_status, upgrade_database

    assert not database_path.exists()

    upgrade_database()

    current, head = get_database_status()
    assert current == (head,)
    assert head == HEAD_REVISION

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "alembic_version",
        "shows",
        "episodes",
        "movies",
        "movie_extras",
        "media_downloads",
        "media_downloads_movie",
        "media_downloads_movie_extra",
        "local_media_profiles_show",
        "local_media_profiles_movie",
        "stream_profiles",
        "stream_profiles_rss",
        "task_schedules",
        "task_runs",
        "task_operations",
        "task_operation_targets",
        "task_operation_runs",
    } <= tables

    task_run_columns = {
        column["name"] for column in inspector.get_columns("task_runs")
    }
    assert "result" in task_run_columns
    operation_columns = {
        column["name"] for column in inspector.get_columns("task_operations")
    }
    assert {
        "kind",
        "source",
        "resource_type",
        "resource_id",
        "status",
        "progress",
        "result",
        "context",
        "notification_seen_at",
    } <= operation_columns

    profile_columns = {
        column["name"] for column in inspector.get_columns("local_media_profiles")
    }
    assert {"type", "append_media_type_to_filename"} <= profile_columns
    profile_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("local_media_profiles")
    }
    settings_index = profile_indexes[
        "uq_local_media_profiles_type_output_template_preferred_format"
    ]
    assert settings_index["column_names"] == [
        "type",
        "output_template",
        "preferred_format",
    ]
    assert bool(settings_index["unique"])

    settings_columns = {
        column["name"] for column in inspector.get_columns("settings")
    }
    assert "onboarding_completed" in settings_columns

    episode_columns = {
        column["name"] for column in inspector.get_columns("episodes")
    }
    assert "metadata_is_final" in episode_columns

    stream_profile_columns = {
        column["name"] for column in inspector.get_columns("stream_profiles")
    }
    assert "ep_id_type_list" in stream_profile_columns

    rss_profile_columns = {
        column["name"] for column in inspector.get_columns("stream_profiles_rss")
    }
    assert {"dw_video_method", "max_items"} <= rss_profile_columns

    podcast_columns = {
        column["name"]
        for column in inspector.get_columns("download_profiles_podcast")
    }
    assert "download_episode_count" in podcast_columns

    with engine.connect() as connection:
        assert not bool(connection.execute(text(
            "SELECT onboarding_completed FROM settings"
        )).scalar_one())
        profiles = connection.execute(text(
            "SELECT type, slug, name, output_template, preferred_format, "
            "append_media_type_to_filename "
            "FROM local_media_profiles ORDER BY slug"
        )).mappings().all()
        assert [dict(profile) for profile in profiles] == [
            {
                "type": "movie",
                "slug": "wireloft-movies",
                "name": "WireLoft Movies",
                "output_template": (
                    "/downloads/movies/{{ movie_title }}/{{ title }}"
                    "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"
                ),
                "preferred_format": "format_1080p",
                "append_media_type_to_filename": False,
            },
            {
                "type": "show",
                "slug": "wireloft-shows-audio",
                "name": "WireLoft Shows (Audio)",
                "output_template": (
                    "/downloads/podcasts/{{ show_title }}/"
                    "{{ episode_published_date }} - {{ episode_title }}.ext"
                ),
                "preferred_format": "format_audio_only",
                "append_media_type_to_filename": False,
            },
            {
                "type": "show",
                "slug": "wireloft-shows-video",
                "name": "WireLoft Shows (Video)",
                "output_template": (
                    "/downloads/shows/{{ show_title }}/{{ season_name }}/"
                    "{{ episode_title }}.ext"
                ),
                "preferred_format": "format_1080p",
                "append_media_type_to_filename": False,
            },
        ]

    movie_columns = {column["name"] for column in inspector.get_columns("movies")}
    assert movie_columns == {
        "id",
        "slug",
        "extended_title",
        "dw_id",
        "sharing_url",
        "author_name",
        "author_slug",
        "logo_image_path",
        "mature_rating",
        "is_downloadable",
        "available_for",
        "release_date",
        "release_date_source",
        "release_date_source_id",
        "release_date_lookup_status",
        "release_date_lookup_attempted_at",
        "release_date_lookup_error",
        "official_trailer_id",
    }

    movie_extra_columns = {
        column["name"] for column in inspector.get_columns("movie_extras")
    }
    assert movie_extra_columns == {
        "id",
        "movie_id",
        "movie_extra_type",
        "dw_id",
        "slug",
        "sharing_url",
        "published_date",
    }

    movie_indexes = {
        index["name"]: index for index in inspector.get_indexes("movies")
    }
    assert "ix_movies_dw_id" in movie_indexes
    assert bool(movie_indexes["ix_movies_dw_id"]["unique"])

    media_download_columns = {
        column["name"] for column in inspector.get_columns("media_downloads")
    }
    assert "attempt_generation" in media_download_columns


def test_0001_is_the_main_branch_schema_baseline(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import get_alembic_config, get_current_revisions

    command.upgrade(get_alembic_config(), BASE_REVISION)

    assert get_current_revisions() == (BASE_REVISION,)
    inspector = inspect(engine)

    # Movie support was the schema accidentally folded into 0001 on develop.
    # The main branch has only the joined-inheritance id and slug columns and no
    # movie-download subtype table.
    assert {
        column["name"] for column in inspector.get_columns("movies")
    } == {"id", "slug"}
    assert "media_downloads_movie" not in set(inspector.get_table_names())

    assert {
        column["name"] for column in inspector.get_columns("settings")
    } == {"id", "created_at", "updated_at"}
    assert {
        column["name"] for column in inspector.get_columns("local_media_profiles")
    } == {
        "id",
        "slug",
        "name",
        "output_template",
        "preferred_format",
        "created_at",
        "updated_at",
    }
    assert "metadata_is_final" not in {
        column["name"] for column in inspector.get_columns("episodes")
    }
    assert "attempt_generation" not in {
        column["name"] for column in inspector.get_columns("media_downloads")
    }
    assert "ep_id_type_list" not in {
        column["name"] for column in inspector.get_columns("stream_profiles")
    }
    assert {
        column["name"] for column in inspector.get_columns("stream_profiles_rss")
    } == {"id", "feed_url"}


def test_upgrade_from_main_baseline_preserves_movie_rows(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import get_alembic_config, upgrade_database
    from backend.db.models import Movie

    command.upgrade(get_alembic_config(), BASE_REVISION)
    with engine.begin() as connection:
        movie_id = connection.execute(text(
            "INSERT INTO media_items "
            "(uuid, type, title, description, downloaded_date, duration, "
            "background_image_path, thumbnail_landscape_path, "
            "thumbnail_portrait_path, thumbnail_square_path) VALUES "
            "('movie-uuid', 'movie', 'A Movie', 'Description', NULL, 5400, "
            "NULL, 'movie-land.jpg', 'movie-port.jpg', 'movie-square.jpg')"
        )).lastrowid
        connection.execute(
            text("INSERT INTO movies (id, slug) VALUES (:id, 'a-movie')"),
            {"id": movie_id},
        )

    upgrade_database()

    with Session(engine) as session:
        movie = session.query(Movie).one()
        assert movie.id == movie_id
        assert movie.slug == "a-movie"
        assert movie.available_for == []
        assert movie.release_date is None
        assert movie.release_date_lookup_status == "pending"
        assert movie.movie_extras == []
        assert movie.official_trailer is None

    command.downgrade(get_alembic_config(), BASE_REVISION)
    inspector = inspect(engine)
    assert {
        column["name"] for column in inspector.get_columns("movies")
    } == {"id", "slug"}
    assert "media_downloads_movie" not in set(inspector.get_table_names())
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT slug FROM movies WHERE id = :id"),
            {"id": movie_id},
        ).scalar_one() == "a-movie"


def test_rss_and_episode_type_data_migrations_from_main_baseline(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import get_alembic_config, upgrade_database

    command.upgrade(get_alembic_config(), BASE_REVISION)
    with engine.begin() as connection:
        show_id = connection.execute(text(
            "INSERT INTO shows "
            "(uuid, slug, title, description, sharing_url, membership_level, "
            "type, episode_identifier, author_name, author_slug) VALUES "
            "('show-uuid', 'show', 'Show', 'Description', "
            "'https://example.test/show', 'FREE', 'podcast', 'numbered', "
            "'Host', 'host')"
        )).lastrowid
        local_media_profile_id = connection.execute(text(
            "INSERT INTO local_media_profiles "
            "(slug, name, output_template, preferred_format) VALUES "
            "('video', 'Video', '/downloads/{show_title}/{episode_title}.ext', "
            "'format_1080p')"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO download_profiles "
            "(show_id, local_media_profile_id, type, enable_profile, ep_id_type_list) "
            "VALUES (:show_id, :profile_id, 'podcast', 1, '[\"ep\"]')"
        ), {
            "show_id": show_id,
            "profile_id": local_media_profile_id,
        })

        dw_profile_id = connection.execute(text(
            "INSERT INTO stream_profiles "
            "(type, show_id, enable_profile, token, use_downloads, use_dw_stream, "
            "preferred_format, require_exact_match) VALUES "
            "('rss', :show_id, 1, 'dw-token', 0, 1, 'format_1080p', 0)"
        ), {"show_id": show_id}).lastrowid
        local_profile_id = connection.execute(text(
            "INSERT INTO stream_profiles "
            "(type, show_id, enable_profile, token, use_downloads, use_dw_stream, "
            "preferred_format, require_exact_match) VALUES "
            "('rss', :show_id, 1, 'local-token', 1, 0, 'format_1080p', 0)"
        ), {"show_id": show_id}).lastrowid
        connection.execute(text(
            "INSERT INTO stream_profiles_rss (id, feed_url) VALUES "
            "(:id, 'https://wireloft.test/dw.xml?custom=value')"
        ), {"id": dw_profile_id})
        connection.execute(text(
            "INSERT INTO stream_profiles_rss (id, feed_url) VALUES "
            "(:id, 'https://wireloft.test/local.xml?dwVideoMethod=cached_mp4&custom=value')"
        ), {"id": local_profile_id})

    upgrade_database()

    with engine.connect() as connection:
        profiles = connection.execute(text(
            "SELECT base.token, base.ep_id_type_list, rss.feed_url, "
            "rss.dw_video_method, rss.max_items "
            "FROM stream_profiles AS base "
            "JOIN stream_profiles_rss AS rss ON rss.id = base.id "
            "ORDER BY base.token"
        )).mappings().all()

    profiles_by_token = {profile["token"]: profile for profile in profiles}
    assert profiles_by_token["dw-token"]["ep_id_type_list"] == ["ep", "aux"]
    assert profiles_by_token["local-token"]["ep_id_type_list"] == ["ep"]
    assert profiles_by_token["dw-token"]["dw_video_method"] == "stream_hls_download_m4a"
    assert profiles_by_token["local-token"]["dw_video_method"] == "stream_hls_download_m4a"
    assert profiles_by_token["dw-token"]["max_items"] == 0
    assert profiles_by_token["local-token"]["max_items"] == 0
    assert parse_qs(urlsplit(profiles_by_token["dw-token"]["feed_url"]).query) == {
        "custom": ["value"],
        "dwVideoMethod": ["stream_hls_download_m4a"],
    }
    assert parse_qs(urlsplit(profiles_by_token["local-token"]["feed_url"]).query) == {
        "custom": ["value"],
    }


def test_upgrade_from_0001_migrates_existing_profiles_to_show_type(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import (
        get_alembic_config,
        get_database_status,
        upgrade_database,
    )
    from backend.db.models import LocalMediaProfileBase, ShowLocalMediaProfile

    command.upgrade(get_alembic_config(), BASE_REVISION)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO local_media_profiles "
            "(id, slug, name, output_template, preferred_format) VALUES "
            "(1, 'audio', 'Audio', '/downloads/{show}/{episode}.ext', "
            "'format_audio_only')"
        ))

    upgrade_database()

    current, head = get_database_status()
    assert current == (head,)
    with Session(engine) as session:
        profile = session.query(LocalMediaProfileBase).filter_by(slug="audio").one()
        assert isinstance(profile, ShowLocalMediaProfile)
        assert profile.type == "show"
        assert session.execute(
            text("SELECT id FROM local_media_profiles_show WHERE id = :id"),
            {"id": profile.id},
        ).scalar_one() == profile.id
        assert bool(session.execute(text(
            "SELECT onboarding_completed FROM settings"
        )).scalar_one())


def test_upgrade_from_0001_rejects_duplicate_profile_settings(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import (
        get_alembic_config,
        get_current_revisions,
        upgrade_database,
    )

    command.upgrade(get_alembic_config(), BASE_REVISION)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO local_media_profiles "
            "(slug, name, output_template, preferred_format) VALUES "
            "('first', 'First', '/downloads/{show}/{episode}.ext', 'format_1080p'), "
            "('second', 'Second', '/downloads/{show}/{episode}.ext', 'format_1080p')"
        ))

    with pytest.raises(RuntimeError, match="must be unique"):
        upgrade_database()

    assert get_current_revisions() == (BASE_REVISION,)
    assert "type" not in {
        column["name"] for column in inspect(engine).get_columns("local_media_profiles")
    }
    assert not {
        "local_media_profiles_show",
        "local_media_profiles_movie",
    } & set(inspect(engine).get_table_names())


def test_local_media_profile_migration_downgrades_to_0001(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import get_alembic_config, upgrade_database

    upgrade_database()
    command.downgrade(get_alembic_config(), BASE_REVISION)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "local_media_profiles_show" not in tables
    assert "local_media_profiles_movie" not in tables
    assert "movie_extras" not in tables
    assert "media_downloads_movie" not in tables
    assert "type" not in {
        column["name"] for column in inspector.get_columns("local_media_profiles")
    }
    assert {
        column["name"] for column in inspector.get_columns("movies")
    } == {"id", "slug"}


def test_upgrade_is_idempotent(migration_database):
    _database_path, _engine = migration_database

    from backend.db.migrations import get_database_status, upgrade_database

    upgrade_database()
    first_status = get_database_status()

    upgrade_database()

    assert get_database_status() == first_status


def test_unmanaged_existing_database_is_rejected(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import DatabaseMigrationError, upgrade_database

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE legacy_table (id INTEGER PRIMARY KEY)"))

    with pytest.raises(DatabaseMigrationError, match="not Alembic-managed"):
        upgrade_database()

    tables = set(inspect(engine).get_table_names())
    assert "legacy_table" in tables
    assert "alembic_version" not in tables


def test_initial_migration_matches_current_orm_metadata(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import check_database, upgrade_database

    upgrade_database()

    # APScheduler owns this table independently in the same SQLite file. Its
    # presence must not make Alembic think a WireLoft migration is missing.
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE apscheduler_jobs ("
            "id VARCHAR(191) PRIMARY KEY, next_run_time FLOAT, job_state BLOB NOT NULL)"
        ))

    check_database()


def test_migration_history_is_main_baseline_plus_wireloft_1_0_and_task_operations():
    from backend.db.migrations import get_alembic_config, get_head_revisions

    scripts = ScriptDirectory.from_config(get_alembic_config())
    revisions = list(scripts.walk_revisions())

    assert get_head_revisions() == (HEAD_REVISION,)
    assert [(revision.revision, revision.down_revision) for revision in revisions] == [
        (HEAD_REVISION, WIRELOFT_1_0_REVISION),
        (WIRELOFT_1_0_REVISION, BASE_REVISION),
        (BASE_REVISION, None),
    ]
    assert revisions[0].doc == "Add durable task operations and structured task results."
    assert revisions[1].doc == "WireLoft 1.0."
