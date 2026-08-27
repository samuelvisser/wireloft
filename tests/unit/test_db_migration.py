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
