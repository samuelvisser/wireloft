from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _make_show(session, *, slug="test-show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Test Show",
        description=None,
        sharing_url=f"https://example.test/{slug}",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_episode(session, show, *, slug, index):
    from backend.db.models import Episode, Season
    from backend.utils.helpers import generate_uuid

    season = Season(show=show, index=index, slug=f"{slug}-season", name="One")
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=f"ep.{index}",
        slug=slug,
        title=f"Episode {slug}",
        duration=100.0,
        publish_status="published_final",
        sharing_url=f"https://example.test/{slug}",
    )
    session.add_all([season, episode])
    session.flush()
    return episode


def _make_local_media_profile(session, *, slug="audio"):
    from backend.db.models import LocalMediaProfile

    profile = LocalMediaProfile(
        slug=slug,
        name=slug,
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format="format_audio_only",
    )
    session.add(profile)
    session.flush()
    return profile


def _make_download(session, episode, lmp, *, status, **overrides):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.media_types import MediaType

    defaults = dict(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=lmp.id,
        download_status=status,
        file_path=f"/downloads/{episode.slug}.m4a",
        progress=0,
    )
    defaults.update(overrides)
    download = EpisodeMediaDownload(**defaults)
    session.add(download)
    session.flush()
    return download


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401 (registers all mappers before create_all)
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def test_resets_a_stuck_downloading_row_and_records_ledger_entry(db_session, monkeypatch):
    from task_manager.tasks.workers.resume_interrupted_downloads import service
    from backend.db.models.media_download import MediaDownloadAttempt

    show = _make_show(db_session)
    episode = _make_episode(db_session, show, slug="ep-stuck", index=1)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc)
    download = _make_download(
        db_session, episode, lmp,
        status="downloading", progress=42, downloaded_bytes=1234, format_downloaded="audio",
        started_at=now, is_redownload_attempt=False,
    )
    db_session.commit()

    triggered = Mock(return_value=0)
    monkeypatch.setattr(service, "trigger_next_pending_downloads", triggered)

    asyncio.run(service.run_resume_interrupted_downloads(db_session))

    db_session.refresh(download)
    assert download.download_status == "pending"
    assert download.progress == 0
    assert download.error_message is None
    assert download.downloaded_bytes is None
    assert download.format_downloaded is None
    assert download.started_at is None
    assert download.finished_at is None

    [entry] = db_session.query(MediaDownloadAttempt).filter_by(media_download_id=download.id).all()
    assert entry.status == "error"
    assert "Interrupted" in entry.error_message
    assert entry.downloaded_bytes == 1234
    assert entry.format_downloaded == "audio"
    assert entry.is_redownload is False

    triggered.assert_called_once_with(db_session)


def test_noop_when_nothing_is_stuck(db_session, monkeypatch):
    from task_manager.tasks.workers.resume_interrupted_downloads import service
    from backend.db.models.media_download import MediaDownloadAttempt

    show = _make_show(db_session)
    episode = _make_episode(db_session, show, slug="ep-ok", index=1)
    lmp = _make_local_media_profile(db_session)
    _make_download(db_session, episode, lmp, status="downloaded")
    db_session.commit()

    triggered = Mock()
    monkeypatch.setattr(service, "trigger_next_pending_downloads", triggered)

    asyncio.run(service.run_resume_interrupted_downloads(db_session))

    triggered.assert_not_called()
    assert db_session.query(MediaDownloadAttempt).count() == 0


def test_ignores_downloads_not_in_downloading_status(db_session, monkeypatch):
    from task_manager.tasks.workers.resume_interrupted_downloads import service

    show = _make_show(db_session)
    lmp = _make_local_media_profile(db_session)
    pending_ep = _make_episode(db_session, show, slug="ep-pending", index=1)
    error_ep = _make_episode(db_session, show, slug="ep-error", index=2)
    downloaded_ep = _make_episode(db_session, show, slug="ep-done", index=3)

    pending = _make_download(db_session, pending_ep, lmp, status="pending")
    errored = _make_download(db_session, error_ep, lmp, status="error", error_message="boom")
    downloaded = _make_download(db_session, downloaded_ep, lmp, status="downloaded")
    db_session.commit()

    triggered = Mock()
    monkeypatch.setattr(service, "trigger_next_pending_downloads", triggered)

    asyncio.run(service.run_resume_interrupted_downloads(db_session))

    triggered.assert_not_called()
    db_session.refresh(pending)
    db_session.refresh(errored)
    db_session.refresh(downloaded)
    assert pending.download_status == "pending"
    assert errored.download_status == "error" and errored.error_message == "boom"
    assert downloaded.download_status == "downloaded"


def test_resets_multiple_stuck_downloads_and_drains_within_budget(db_session, monkeypatch):
    from config import get_settings
    from task_manager.tasks.workers.resume_interrupted_downloads import service

    show = _make_show(db_session)
    lmp = _make_local_media_profile(db_session)
    downloads = [
        _make_download(db_session, _make_episode(db_session, show, slug=f"ep{i}", index=i), lmp, status="downloading")
        for i in range(3)
    ]
    db_session.commit()

    monkeypatch.setattr(get_settings().download_settings, "max_concurrent_downloads", 1)
    real_trigger_now = Mock()
    from task_manager.tasks.workers.download_profile_worker import _helpers as profile_helpers
    monkeypatch.setattr(profile_helpers, "trigger_now", real_trigger_now)

    asyncio.run(service.run_resume_interrupted_downloads(db_session))

    for d in downloads:
        db_session.refresh(d)
    assert all(d.download_status == "pending" for d in downloads)
    # Only one slot was available, so only one of the three got re-triggered
    assert real_trigger_now.call_count == 1
