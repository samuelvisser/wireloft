from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session


def _create_all_tables(engine):
    import backend.db.models  # noqa: F401 (registers all mappers)
    from backend.db import Base

    Base.metadata.create_all(engine)


def test_recreate_outdated_empty_tables_adds_missing_nullable_column_in_place(tmp_path: Path):
    """A nullable column added to the ORM model (like downloaded_publish_status)
    must be applied to an existing, non-empty database via ALTER TABLE, not by
    refusing to start or silently dropping the user's data."""
    from backend.db.core import _recreate_outdated_empty_tables
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    db_path = tmp_path / "migration-test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_all_tables(engine)

    # Simulate a database created before downloaded_publish_status existed.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE media_downloads_episode DROP COLUMN downloaded_publish_status"))

    session = Session(engine)
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid

    show = Show(
        uuid="show-uuid", slug="show", title="Show", description=None,
        sharing_url="https://example.test/show", membership_level="FREE",
        type=ShowType.PODCAST.value, episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host", author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    episode = Episode(
        uuid=generate_uuid(), type="episode", show=show, season=season, index=1,
        episode_identifier="ep.1", slug="ep-1", title="Ep 1", duration=100.0,
        publish_status="published_final", sharing_url="https://example.test/ep-1",
    )
    lmp = LocalMediaProfile(slug="audio", name="Audio", output_template="/downloads/{episode}.ext", preferred_format="format_audio_only")
    session.add_all([show, season, episode, lmp])
    session.commit()

    session.execute(text(
        "INSERT INTO media_downloads (type, media_item_id, local_media_profile_id, download_status, file_path, progress) "
        "VALUES (:type, :media_item_id, :lmp_id, :status, :path, 0)"
    ), {"type": MediaType.EPISODE.value, "media_item_id": episode.id, "lmp_id": lmp.id, "status": MediaDownloadStatus.DOWNLOADED.value, "path": "/downloads/ep-1.m4a"})
    download_id = session.execute(text("SELECT id FROM media_downloads")).scalar_one()
    session.execute(text("INSERT INTO media_downloads_episode (id) VALUES (:id)"), {"id": download_id})
    session.commit()
    session.close()

    # Sanity check: the old schema really is missing the column before migrating.
    columns_before = {c["name"] for c in inspect(engine).get_columns("media_downloads_episode")}
    assert "downloaded_publish_status" not in columns_before

    _recreate_outdated_empty_tables(engine)

    columns_after = {c["name"] for c in inspect(engine).get_columns("media_downloads_episode")}
    assert "downloaded_publish_status" in columns_after

    # The pre-existing row must have survived, with the new column backfilled as NULL.
    session = Session(engine)
    from backend.db.models.media_download import EpisodeMediaDownload

    row = session.query(EpisodeMediaDownload).one()
    assert row.id == download_id
    assert row.file_path == "/downloads/ep-1.m4a"
    assert row.downloaded_publish_status is None

    # And it must be fully usable going forward (including via the ORM).
    row.downloaded_publish_status = "published_final"
    session.commit()
    session.close()

    engine.dispose()


def test_recreate_outdated_empty_tables_still_drops_empty_outdated_tables(tmp_path: Path):
    """An empty table with an outdated schema keeps using the drop+recreate
    path (there is no data at risk), regardless of which columns changed."""
    from backend.db.core import _recreate_outdated_empty_tables

    db_path = tmp_path / "empty-migration-test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_all_tables(engine)

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE media_downloads_episode DROP COLUMN downloaded_publish_status"))

    # Mirrors create_tables(): the empty-table path only drops; create_all
    # recreates it from the current model on the very next call, same as at
    # real startup.
    _recreate_outdated_empty_tables(engine)
    _create_all_tables(engine)

    columns_after = {c["name"] for c in inspect(engine).get_columns("media_downloads_episode")}
    assert "downloaded_publish_status" in columns_after

    engine.dispose()


def test_recreate_outdated_empty_tables_raises_for_non_nullable_gap_with_data(tmp_path: Path, monkeypatch):
    """A genuinely unsafe schema gap (a missing NOT NULL column on a non-empty
    table) must still refuse to auto-migrate rather than guess a default."""
    from backend.db.core import _recreate_outdated_empty_tables
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    db_path = tmp_path / "unsafe-migration-test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_all_tables(engine)

    # download_status is NOT NULL on the model; drop it to simulate a breaking change.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE media_downloads DROP COLUMN download_status"))
        conn.execute(text(
            "INSERT INTO media_downloads (type, media_item_id, local_media_profile_id, file_path, progress) "
            "VALUES (:type, 1, 1, '/downloads/x.m4a', 0)"
        ), {"type": MediaType.EPISODE.value})

    with pytest.raises(RuntimeError, match="download_status"):
        _recreate_outdated_empty_tables(engine)

    engine.dispose()


def test_recreate_outdated_empty_tables_adds_token_to_empty_stream_profiles(tmp_path: Path):
    """stream_profiles.token is new and non-nullable; an empty pre-token table
    (the realistic case, since RSS feeds are a brand new feature) is dropped
    and recreated rather than refused."""
    from backend.db.core import _recreate_outdated_empty_tables

    db_path = tmp_path / "stream-profile-migration-test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_all_tables(engine)

    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_stream_profiles_token"))
        conn.execute(text("ALTER TABLE stream_profiles DROP COLUMN token"))

    columns_before = {c["name"] for c in inspect(engine).get_columns("stream_profiles")}
    assert "token" not in columns_before

    _recreate_outdated_empty_tables(engine)
    _create_all_tables(engine)

    columns_after = {c["name"] for c in inspect(engine).get_columns("stream_profiles")}
    assert "token" in columns_after

    engine.dispose()


def test_recreate_outdated_empty_tables_raises_for_populated_stream_profiles_missing_token(tmp_path: Path):
    """A non-empty stream_profiles table missing the new non-nullable token
    column must refuse to auto-migrate, same as any other unsafe gap."""
    from backend.db.core import _recreate_outdated_empty_tables

    db_path = tmp_path / "stream-profile-unsafe-migration-test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_all_tables(engine)

    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_stream_profiles_token"))
        conn.execute(text("ALTER TABLE stream_profiles DROP COLUMN token"))

    session = Session(engine)
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid="show-uuid", slug="show", title="Show", description=None,
        sharing_url="https://example.test/show", membership_level="FREE",
        type=ShowType.PODCAST.value, episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host", author_slug="host",
    )
    session.add(show)
    session.flush()
    session.execute(text(
        "INSERT INTO stream_profiles (type, show_id, enable_profile, use_downloads, use_dw_stream, "
        "preferred_format, require_exact_match) VALUES ('rss', :show_id, 1, 1, 0, 'format_1080p', 0)"
    ), {"show_id": show.id})
    session.commit()
    session.close()

    with pytest.raises(RuntimeError, match="token"):
        _recreate_outdated_empty_tables(engine)

    engine.dispose()


def test_recreate_outdated_empty_tables_adds_is_no_show_today_to_populated_episodes(tmp_path: Path):
    """The exact real-world case this was added for: episodes.is_no_show_today
    is a new nullable column on a table real users already have populated."""
    from backend.db.core import _recreate_outdated_empty_tables
    from backend.types.show_types import EpisodeIdentifier, ShowType

    db_path = tmp_path / "episodes-migration-test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_all_tables(engine)

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE episodes DROP COLUMN is_no_show_today"))

    session = Session(engine)
    from backend.db.models import Episode, Season, Show
    from backend.utils.helpers import generate_uuid

    show = Show(
        uuid="show-uuid", slug="show", title="Show", description=None,
        sharing_url="https://example.test/show", membership_level="FREE",
        type=ShowType.PODCAST.value, episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host", author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add_all([show, season])
    session.flush()
    session.execute(text(
        "INSERT INTO media_items (uuid, type, title, duration) VALUES (:uuid, 'episode', 'Ep', 100.0)"
    ), {"uuid": generate_uuid()})
    media_item_id = session.execute(text("SELECT id FROM media_items")).scalar_one()
    session.execute(text(
        "INSERT INTO episodes (id, show_id, season_id, \"index\", episode_identifier, slug, publish_status, sharing_url) "
        "VALUES (:id, :show_id, :season_id, 1, 'ep.1', 'ep-1', 'published_final', 'https://example.test/ep-1')"
    ), {"id": media_item_id, "show_id": show.id, "season_id": season.id})
    session.commit()
    session.close()

    columns_before = {c["name"] for c in inspect(engine).get_columns("episodes")}
    assert "is_no_show_today" not in columns_before

    _recreate_outdated_empty_tables(engine)

    columns_after = {c["name"] for c in inspect(engine).get_columns("episodes")}
    assert "is_no_show_today" in columns_after

    session = Session(engine)
    episode = session.query(Episode).one()
    assert episode.slug == "ep-1"
    assert episode.is_no_show_today is None
    session.close()

    engine.dispose()
