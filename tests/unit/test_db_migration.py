from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


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
    assert head == "a59b07916fb6"

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "alembic_version",
        "shows",
        "episodes",
        "movies",
        "trailers",
        "media_downloads",
        "media_downloads_movie",
        "local_media_profiles_show",
        "local_media_profiles_movie",
        "task_schedules",
        "task_runs",
    } <= tables

    profile_columns = {
        column["name"] for column in inspector.get_columns("local_media_profiles")
    }
    assert "type" in profile_columns
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
    }

    trailer_columns = {
        column["name"] for column in inspector.get_columns("trailers")
    }
    assert trailer_columns == {
        "id",
        "movie_id",
        "dw_id",
        "slug",
        "sharing_url",
    }

    movie_indexes = {index["name"]: index for index in inspector.get_indexes("movies")}
    assert "ix_movies_dw_id" in movie_indexes
    assert bool(movie_indexes["ix_movies_dw_id"]["unique"])


def test_trailer_migration_preserves_legacy_movie_trailer_metadata(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import (
        get_alembic_config,
        get_database_status,
        upgrade_database,
    )
    from backend.db.models import Movie, Trailer

    command.upgrade(get_alembic_config(), "828421f64d03")
    with engine.begin() as connection:
        result = connection.execute(text(
            "INSERT INTO media_items "
            "(uuid, type, title, description, downloaded_date, duration, "
            "background_image_path, thumbnail_landscape_path, "
            "thumbnail_portrait_path, thumbnail_square_path) VALUES "
            "('movie-uuid', 'movie', 'A Movie', 'Description', NULL, 5400, "
            "NULL, 'movie-land.jpg', 'movie-port.jpg', 'movie-square.jpg')"
        ))
        movie_id = result.lastrowid
        connection.execute(text(
            "INSERT INTO movies "
            "(id, slug, extended_title, dw_id, sharing_url, author_name, "
            "mature_rating, is_downloadable, trailer_slug, trailer_title, "
            "trailer_sharing_url, trailer_thumbnail_path) VALUES "
            "(:id, 'a-movie', 'A Movie Extended', 'movie-1', "
            "'https://example.test/a-movie', 'A Director', 'PG-13', 1, "
            "'a-movie-trailer', 'A Movie Trailer', "
            "'https://example.test/a-movie-trailer', 'trailer.jpg')"
        ), {"id": movie_id})

    upgrade_database()

    current, head = get_database_status()
    assert current == (head,)
    with Session(engine) as session:
        movie = session.query(Movie).one()
        trailer = session.query(Trailer).one()
        assert movie.available_for == []
        assert movie.trailers == [trailer]
        assert trailer.movie_id == movie.id
        assert trailer.type == "trailer"
        assert trailer.slug == "a-movie-trailer"
        assert trailer.title == "A Movie Trailer"
        assert trailer.sharing_url == "https://example.test/a-movie-trailer"
        assert trailer.thumbnail_landscape_path == "trailer.jpg"

    command.downgrade(get_alembic_config(), "828421f64d03")

    inspector = inspect(engine)
    assert "trailers" not in inspector.get_table_names()
    with engine.connect() as connection:
        legacy = connection.execute(text(
            "SELECT trailer_slug, trailer_title, trailer_sharing_url, "
            "trailer_thumbnail_path FROM movies WHERE id = :id"
        ), {"id": movie_id}).mappings().one()
    assert dict(legacy) == {
        "trailer_slug": "a-movie-trailer",
        "trailer_title": "A Movie Trailer",
        "trailer_sharing_url": "https://example.test/a-movie-trailer",
        "trailer_thumbnail_path": "trailer.jpg",
    }
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM media_items WHERE type = 'trailer'"
        )).scalar_one() == 0


def test_upgrade_from_0001_migrates_existing_profiles_to_show_type(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import (
        get_alembic_config,
        get_database_status,
        upgrade_database,
    )
    from backend.db.models import LocalMediaProfileBase, ShowLocalMediaProfile

    command.upgrade(get_alembic_config(), "0001")
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
        profile = session.query(LocalMediaProfileBase).one()
        assert isinstance(profile, ShowLocalMediaProfile)
        assert profile.type == "show"
        assert session.execute(
            text("SELECT id FROM local_media_profiles_show")
        ).scalar_one() == profile.id


def test_upgrade_from_0001_rejects_duplicate_profile_settings(migration_database):
    _database_path, engine = migration_database

    from backend.db.migrations import (
        get_alembic_config,
        get_current_revisions,
        upgrade_database,
    )

    command.upgrade(get_alembic_config(), "0001")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO local_media_profiles "
            "(slug, name, output_template, preferred_format) VALUES "
            "('first', 'First', '/downloads/{show}/{episode}.ext', 'format_1080p'), "
            "('second', 'Second', '/downloads/{show}/{episode}.ext', 'format_1080p')"
        ))

    with pytest.raises(RuntimeError, match="must be unique"):
        upgrade_database()

    assert get_current_revisions() == ("0001",)
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
    command.downgrade(get_alembic_config(), "0001")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "local_media_profiles_show" not in tables
    assert "local_media_profiles_movie" not in tables
    assert "type" not in {
        column["name"] for column in inspector.get_columns("local_media_profiles")
    }
    assert "extended_title" not in {
        column["name"] for column in inspector.get_columns("movies")
    }


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
        connection.execute(
            text(
                "CREATE TABLE apscheduler_jobs ("
                "id VARCHAR(191) PRIMARY KEY, next_run_time FLOAT, job_state BLOB NOT NULL)"
            )
        )

    check_database()


def test_migration_history_has_exactly_one_head():
    from backend.db.migrations import get_head_revisions

    assert get_head_revisions() == ("a59b07916fb6",)
