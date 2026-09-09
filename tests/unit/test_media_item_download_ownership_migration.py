from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


PREVIOUS_REVISION = "c5a9e2f7b104"
REVISION = "d8f3a1c6b205"


def test_media_item_download_ownership_migration_upgrades_from_c5_and_downgrades(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.db import core
    from backend.db.migrations import (
        downgrade_database,
        get_alembic_config,
        get_current_revisions,
        upgrade_database,
    )

    database_path = tmp_path / "media-item-download-ownership.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    command.upgrade(get_alembic_config(), PREVIOUS_REVISION)

    with engine.begin() as connection:
        show_id = connection.execute(text(
            "INSERT INTO shows "
            "(uuid, slug, title, description, sharing_url, membership_level, "
            "type, episode_identifier, author_name, author_slug) VALUES "
            "('show-uuid', 'show', 'Show', 'Description', "
            "'https://example.test/show', 'FREE', 'podcast', 'numbered', "
            "'Host', 'host')"
        )).lastrowid
        season_id = connection.execute(text(
            "INSERT INTO seasons (show_id, \"index\", slug, name) "
            "VALUES (:show_id, 1, 'season-1', 'Season 1')"
        ), {"show_id": show_id}).lastrowid
        episode_id = connection.execute(text(
            "INSERT INTO media_items (uuid, type, downloaded_date) "
            "VALUES ('episode-uuid', 'episode', '2026-09-01 10:00:00+00:00')"
        )).lastrowid
        connection.execute(text(
            "INSERT INTO media_items_episodes "
            "(id, show_id, season_id, \"index\", episode_identifier, slug, "
            "publish_status, sharing_url, title, description, duration, redownloaded_date) "
            "VALUES (:id, :show_id, :season_id, 1, 'ep.1', 'episode-1', "
            "'published_final', 'https://example.test/episode-1', "
            "'Episode 1', 'Description', 1800, '2026-09-02 10:00:00+00:00')"
        ), {
            "id": episode_id,
            "show_id": show_id,
            "season_id": season_id,
        })
        connection.execute(text(
            "INSERT INTO metadata (parent_table, parent_id, key, value) "
            "VALUES ('media_items_episodes', :episode_id, 'migration.test', 'preserved')"
        ), {"episode_id": episode_id})

        profile_id = connection.execute(text(
            "SELECT id FROM local_media_profiles WHERE slug = 'wireloft-shows-video'"
        )).scalar_one()
        series_profile_id = connection.execute(text(
            "INSERT INTO download_profiles "
            "(show_id, local_media_profile_id, type, enable_profile, ep_id_type_list) "
            "VALUES (:show_id, :profile_id, 'series', 1, '[]')"
        ), {
            "show_id": show_id,
            "profile_id": profile_id,
        }).lastrowid
        connection.execute(
            text(
                "INSERT INTO download_profiles_series (id, include_upcoming_seasons) "
                "VALUES (:id, 1)"
            ),
            {"id": series_profile_id},
        )
        connection.execute(text(
            "INSERT INTO download_profile_series_seasons "
            "(series_download_profile_id, season_id) VALUES (:profile_id, :season_id)"
        ), {
            "profile_id": series_profile_id,
            "season_id": season_id,
        })

        download_id = connection.execute(text(
            "INSERT INTO media_downloads "
            "(type, media_item_id, local_media_profile_id, file_path, "
            "artifact_status, downloaded_at) VALUES "
            "('episode', :episode_id, :profile_id, '/downloads/episode-1.mp4', "
            "'available', '2026-09-03 10:00:00+00:00')"
        ), {
            "episode_id": episode_id,
            "profile_id": profile_id,
        }).lastrowid
        connection.execute(
            text("INSERT INTO media_downloads_episode (id) VALUES (:id)"),
            {"id": download_id},
        )

    upgrade_database()

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "media_items_episode",
        "media_items_movie",
        "media_items_movie_extra",
    } <= tables
    assert {
        "alembic_version",
        "media_items_episodes",
        "media_items_movies",
        "media_items_movie_extras",
    }.isdisjoint(tables)
    assert "downloaded_date" not in {
        column["name"] for column in inspector.get_columns("media_items")
    }
    assert "redownloaded_date" not in {
        column["name"] for column in inspector.get_columns("media_items_episode")
    }
    assert {
        column["name"]
        for column in inspector.get_columns("download_profile_series_seasons")
    } == {"download_profiles_series_id", "season_id"}
    assert "alembic_version_num" in {
        column["name"] for column in inspector.get_columns("settings")
    }
    assert get_current_revisions() == (REVISION,)

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT parent_table FROM metadata "
            "WHERE parent_id = :episode_id AND key = 'migration.test'"
        ), {"episode_id": episode_id}).scalar_one() == "media_items_episode"
        assert connection.execute(text(
            "SELECT download_profiles_series_id FROM download_profile_series_seasons "
            "WHERE season_id = :season_id"
        ), {"season_id": season_id}).scalar_one() == series_profile_id
        assert connection.execute(text(
            "SELECT downloaded_at FROM media_downloads WHERE id = :download_id"
        ), {"download_id": download_id}).scalar_one() is not None
        assert connection.execute(text(
            "SELECT alembic_version_num FROM settings"
        )).scalar_one() == REVISION

    # Current ORM mappings must work against the post-migration physical names,
    # including HasMetadataMixin's table-name discriminator.
    import backend.db.models  # noqa: F401
    from backend.db.models import Episode
    from backend.db.models.media_download import EpisodeMediaDownload

    with Session(engine) as session:
        episode = session.get(Episode, (episode_id, show_id))
        assert episode is not None
        assert episode.title == "Episode 1"
        assert episode.get_meta("migration.test") == "preserved"
        assert not hasattr(episode, "downloaded_date")
        assert not hasattr(episode, "redownloaded_date")
        download = session.get(EpisodeMediaDownload, download_id)
        assert download is not None
        assert download.downloaded_at is not None

    downgrade_database(PREVIOUS_REVISION)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "alembic_version" in tables
    assert {
        "media_items_episodes",
        "media_items_movies",
        "media_items_movie_extras",
    } <= tables
    assert {
        "media_items_episode",
        "media_items_movie",
        "media_items_movie_extra",
    }.isdisjoint(tables)
    assert "downloaded_date" in {
        column["name"] for column in inspector.get_columns("media_items")
    }
    assert "redownloaded_date" in {
        column["name"] for column in inspector.get_columns("media_items_episodes")
    }
    assert {
        column["name"]
        for column in inspector.get_columns("download_profile_series_seasons")
    } == {"series_download_profile_id", "season_id"}
    assert "alembic_version_num" not in {
        column["name"] for column in inspector.get_columns("settings")
    }
    assert get_current_revisions() == (PREVIOUS_REVISION,)

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT parent_table FROM metadata "
            "WHERE parent_id = :episode_id AND key = 'migration.test'"
        ), {"episode_id": episode_id}).scalar_one() == "media_items_episodes"
        assert connection.execute(text(
            "SELECT series_download_profile_id FROM download_profile_series_seasons "
            "WHERE season_id = :season_id"
        ), {"season_id": season_id}).scalar_one() == series_profile_id
        restored = connection.execute(text(
            "SELECT media_items.downloaded_date, media_items_episodes.redownloaded_date "
            "FROM media_items JOIN media_items_episodes "
            "ON media_items_episodes.id = media_items.id "
            "WHERE media_items.id = :episode_id"
        ), {"episode_id": episode_id}).one()
        assert restored.downloaded_date is None
        assert restored.redownloaded_date is None
        assert connection.execute(text(
            "SELECT downloaded_at FROM media_downloads WHERE id = :download_id"
        ), {"download_id": download_id}).scalar_one() is not None

    engine.dispose()