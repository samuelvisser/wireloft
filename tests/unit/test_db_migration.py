from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


HEAD_REVISION = "d8f3a1c6b205"
CONSOLIDATED_MEDIA_ITEM_REVISION = "c5a9e2f7b104"
MOVIE_EXTRA_IDENTITY_REVISION = "c9f2d8a1b604"
MOVIE_PAGE_METADATA_REVISION = "a8e4c1d7f203"
ARTIFACT_IDENTITY_REVISION = "c1f7b9e4d205"
SHOW_PROFILE_SCOPE_REVISION = "e3a1b5c7d902"
EPISODE_CANONICAL_REVISION = "a4d7c2e9f610"
EPISODE_RELEASE_REVISION = "e6a9c1f4b203"
DATETIME_CONTRACT_REVISION = "e3a8f4c9b102"
DROP_DOWNLOAD_ATTEMPTS_REVISION = "b7e2c4d9a601"
DOWNLOAD_EXECUTION_REVISION = "f2c7a4e8b901"
TASK_OPERATIONS_REVISION = "d4f0a9c2e713"
WIRELOFT_1_0_REVISION = "c8d4e2f1a7b9"
BASE_REVISION = "0001"

CONTENT_METADATA_FIELDS = frozenset({
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
})


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
        "shows",
        "media_items_episode",
        "media_items_movie",
        "media_items_movie_extra",
        "movie_extra_sources",
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
    assert {
        "alembic_version",
        "episodes",
        "movies",
        "movie_extras",
        "media_items_episodes",
        "media_items_movies",
        "media_items_movie_extras",
    }.isdisjoint(tables)

    task_run_columns = {column["name"] for column in inspector.get_columns("task_runs")}
    assert "result" in task_run_columns
    operation_columns = {column["name"] for column in inspector.get_columns("task_operations")}
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

    profile_columns = {column["name"] for column in inspector.get_columns("local_media_profiles")}
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

    settings_columns = {column["name"] for column in inspector.get_columns("settings")}
    assert settings_columns == {
        "id",
        "onboarding_completed",
        "alembic_version_num",
        "created_at",
        "updated_at",
    }

    media_item_columns = {
        column["name"] for column in inspector.get_columns("media_items")
    }
    assert media_item_columns == {
        "id",
        "uuid",
        "type",
        "created_at",
        "updated_at",
    }

    episode_columns = {
        column["name"]
        for column in inspector.get_columns("media_items_episode")
    }
    assert "metadata_is_final" in episode_columns
    assert "redownloaded_date" not in episode_columns
    assert CONTENT_METADATA_FIELDS <= episode_columns

    series_season_columns = {
        column["name"]
        for column in inspector.get_columns("download_profile_series_seasons")
    }
    assert series_season_columns == {"download_profiles_series_id", "season_id"}

    stream_profile_columns = {column["name"] for column in inspector.get_columns("stream_profiles")}
    assert "ep_id_type_list" in stream_profile_columns

    rss_profile_columns = {column["name"] for column in inspector.get_columns("stream_profiles_rss")}
    assert {"dw_video_method", "max_items"} <= rss_profile_columns

    podcast_columns = {
        column["name"]
        for column in inspector.get_columns("download_profiles_podcast")
    }
    assert "download_episode_count" in podcast_columns

    with engine.connect() as connection:
        settings = connection.execute(text(
            "SELECT onboarding_completed, alembic_version_num FROM settings"
        )).mappings().one()
        assert not bool(settings["onboarding_completed"])
        assert settings["alembic_version_num"] == HEAD_REVISION
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

    movie_columns = {
        column["name"]
        for column in inspector.get_columns("media_items_movie")
    }
    assert movie_columns == {
        "id",
        "slug",
        "extended_title",
        "sharing_url",
        "author_name",
        "author_slug",
        "logo_image_path",
        "mature_rating",
        "has_video",
        "is_downloadable",
        "status",
        "published_at",
        "background",
        "byline",
        "language",
        "origin_country",
        "images",
        "available_for",
        "cast_and_crew",
        "directed_by",
        "genres",
        "hosts",
        "production_companies",
        "starring",
        "written_by",
        "release_date",
        "release_date_source",
        "release_date_source_id",
        "release_date_lookup_status",
        "release_date_lookup_attempted_at",
        "release_date_lookup_error",
        "official_trailer_id",
    } | CONTENT_METADATA_FIELDS

    movie_extra_source_columns = {
        column["name"] for column in inspector.get_columns("movie_extra_sources")
    }
    assert movie_extra_source_columns == {
        "id",
        "slug",
        "sharing_url",
        "published_date",
        "available_for",
    } | CONTENT_METADATA_FIELDS
    movie_extra_source_unique_constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints("movie_extra_sources")
    }
    assert movie_extra_source_unique_constraints[
        "uq_movie_extra_sources_slug"
    ]["column_names"] == ["slug"]

    movie_extra_columns = {
        column["name"]
        for column in inspector.get_columns("media_items_movie_extra")
    }
    assert movie_extra_columns == {
        "id",
        "movie_id",
        "source_id",
        "movie_extra_type",
    }
    movie_extra_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("media_items_movie_extra")
    }
    assert "ix_movie_extras_dw_id" not in movie_extra_indexes
    assert "ix_movie_extras_slug" not in movie_extra_indexes
    assert not bool(movie_extra_indexes["ix_movie_extras_source_id"]["unique"])
    movie_extra_unique_constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints("media_items_movie_extra")
    }
    assert "uq_movie_extras_movie_id_dw_id" not in movie_extra_unique_constraints
    assert "uq_movie_extras_movie_id_slug" not in movie_extra_unique_constraints
    assert movie_extra_unique_constraints[
        "uq_movie_extras_movie_id_source_id"
    ]["column_names"] == ["movie_id", "source_id"]
    source_fk = next(
        foreign_key
        for foreign_key in inspector.get_foreign_keys("media_items_movie_extra")
        if foreign_key["constrained_columns"] == ["source_id"]
    )
    assert source_fk["referred_table"] == "movie_extra_sources"
    assert source_fk["referred_columns"] == ["id"]

    movie_indexes = {
        index["name"]: index
        for index in inspector.get_indexes("media_items_movie")
    }
    assert "ix_movies_dw_id" not in movie_indexes

    media_download_columns = {
        column["name"] for column in inspector.get_columns("media_downloads")
    }
    assert {
        "artifact_status",
        "artifact_error",
        "automatic_retry_suppressed",
        "downloaded_at",
        "downloaded_bytes",
        "format_downloaded",
    } <= media_download_columns
    assert {
        "download_status",
        "progress",
        "error_message",
        "started_at",
        "finished_at",
        "attempt_generation",
    }.isdisjoint(media_download_columns)
    episode_download_columns = {
        column["name"] for column in inspector.get_columns("media_downloads_episode")
    }
    assert "is_redownload_attempt" not in episode_download_columns


def test_0001_is_the_main_branch_schema_baseline(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import get_alembic_config, get_current_revisions

    command.upgrade(get_alembic_config(), BASE_REVISION)

    assert get_current_revisions() == (BASE_REVISION,)
    inspector = inspect(engine)

    assert {column["name"] for column in inspector.get_columns("movies")} == {"id", "slug"}
    assert "media_downloads_movie" not in set(inspector.get_table_names())

    assert {column["name"] for column in inspector.get_columns("settings")} == {"id", "created_at", "updated_at"}
    assert {column["name"] for column in inspector.get_columns("local_media_profiles")} == {
        "id",
        "slug",
        "name",
        "output_template",
        "preferred_format",
        "created_at",
        "updated_at",
    }
    assert "metadata_is_final" not in {column["name"] for column in inspector.get_columns("episodes")}
    assert "attempt_generation" not in {column["name"] for column in inspector.get_columns("media_downloads")}
    assert "ep_id_type_list" not in {column["name"] for column in inspector.get_columns("stream_profiles")}
    assert {column["name"] for column in inspector.get_columns("stream_profiles_rss")} == {"id", "feed_url"}


def test_upgrade_from_main_baseline_preserves_movie_rows(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import downgrade_database, get_alembic_config, upgrade_database
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
        assert movie.title == "A Movie"
        assert movie.description == "Description"
        assert movie.duration == 5400
        assert movie.thumbnail_landscape_path == "movie-land.jpg"
        assert movie.thumbnail_portrait_path == "movie-port.jpg"
        assert movie.thumbnail_square_path == "movie-square.jpg"
        assert movie.has_video is False
        assert movie.status is None
        assert movie.images == {}
        assert movie.available_for == []
        assert movie.cast_and_crew == []
        assert movie.directed_by == []
        assert movie.hosts == []
        assert movie.starring == []
        assert movie.written_by == []
        assert movie.release_date is None
        assert movie.release_date_lookup_status == "pending"
        assert movie.movie_extras == []
        assert movie.official_trailer is None

    downgrade_database(BASE_REVISION)
    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("movies")} == {"id", "slug"}
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
    assert "type" not in {column["name"] for column in inspect(engine).get_columns("local_media_profiles")}
    assert not {"local_media_profiles_show", "local_media_profiles_movie"} & set(inspect(engine).get_table_names())


def test_local_media_profile_migration_downgrades_to_0001(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import downgrade_database, upgrade_database

    upgrade_database()
    downgrade_database(BASE_REVISION)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "local_media_profiles_show" not in tables
    assert "local_media_profiles_movie" not in tables
    assert "movie_extras" not in tables
    assert "movie_extra_sources" not in tables
    assert "media_downloads_movie" not in tables
    assert "type" not in {column["name"] for column in inspector.get_columns("local_media_profiles")}
    assert {column["name"] for column in inspector.get_columns("movies")} == {"id", "slug"}
    assert "alembic_version" in tables


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

    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE apscheduler_jobs ("
            "id VARCHAR(191) PRIMARY KEY, next_run_time FLOAT, job_state BLOB NOT NULL)"
        ))

    check_database()


def test_migration_history_is_linear_through_media_download_ownership():
    from backend.db.migrations import get_alembic_config, get_head_revisions

    scripts = ScriptDirectory.from_config(get_alembic_config())
    revisions = list(scripts.walk_revisions())

    assert get_head_revisions() == (HEAD_REVISION,)
    assert [(revision.revision, revision.down_revision) for revision in revisions] == [
        (HEAD_REVISION, CONSOLIDATED_MEDIA_ITEM_REVISION),
        (CONSOLIDATED_MEDIA_ITEM_REVISION, MOVIE_EXTRA_IDENTITY_REVISION),
        (MOVIE_EXTRA_IDENTITY_REVISION, MOVIE_PAGE_METADATA_REVISION),
        (MOVIE_PAGE_METADATA_REVISION, ARTIFACT_IDENTITY_REVISION),
        (ARTIFACT_IDENTITY_REVISION, SHOW_PROFILE_SCOPE_REVISION),
        (SHOW_PROFILE_SCOPE_REVISION, EPISODE_CANONICAL_REVISION),
        (EPISODE_CANONICAL_REVISION, EPISODE_RELEASE_REVISION),
        (EPISODE_RELEASE_REVISION, DATETIME_CONTRACT_REVISION),
        (DATETIME_CONTRACT_REVISION, DROP_DOWNLOAD_ATTEMPTS_REVISION),
        (DROP_DOWNLOAD_ATTEMPTS_REVISION, DOWNLOAD_EXECUTION_REVISION),
        (DOWNLOAD_EXECUTION_REVISION, TASK_OPERATIONS_REVISION),
        (TASK_OPERATIONS_REVISION, WIRELOFT_1_0_REVISION),
        (WIRELOFT_1_0_REVISION, BASE_REVISION),
        (BASE_REVISION, None),
    ]
    assert revisions[0].doc == "Finalize media-item naming, download ownership, and database metadata."
    assert revisions[1].doc == "Consolidate media-item storage after movie-extra identity."
    assert revisions[2].doc == "Scope movie-extra identity to its parent movie."
    assert revisions[3].doc == "Persist canonical Daily Wire movie-page metadata."
