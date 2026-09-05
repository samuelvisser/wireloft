from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
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


def _make_season(session, show, *, index=1, slug="season-1", name="One"):
    from backend.db.models import Season

    season = Season(show=show, index=index, slug=slug, name=name)
    session.add(season)
    session.flush()
    return season


def _make_episode(session, show, season, *, slug, ep_id, status, published_at, index):
    from backend.db.models import Episode
    from backend.utils.helpers import generate_uuid

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=ep_id,
        slug=slug,
        title=f"Episode {slug}",
        duration=100.0,
        publish_status=status,
        sharing_url=f"https://example.test/{slug}",
        published_date=published_at,
    )
    session.add(episode)
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


def _make_podcast_profile(session, show, lmp, **overrides):
    from backend.db.models.download_profile import PodcastDownloadProfile
    from backend.types.download_profile_types import EpIdType

    defaults = dict(
        show=show,
        local_media_profile=lmp,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=0,
        delete_older_episodes=False,
    )
    defaults.update(overrides)
    profile = PodcastDownloadProfile(**defaults)
    session.add(profile)
    session.flush()
    return profile


def _make_series_profile(session, show, lmp, seasons, **overrides):
    from backend.db.models.download_profile import SeriesDownloadProfile
    from backend.types.download_profile_types import EpIdType

    defaults = dict(
        show=show,
        local_media_profile=lmp,
        type="series",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value],
        include_upcoming_seasons=False,
    )
    defaults.update(overrides)
    profile = SeriesDownloadProfile(**defaults)
    profile.seasons = seasons
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture
def db_session(monkeypatch, tmp_path):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from config import get_settings

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    yield session
    session.close()
    engine.dispose()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _completed_download(db_session, episode, lmp, profile, *, publish_status="published_final"):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=lmp.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        downloaded_publish_status=publish_status,
        file_path="/downloads/existing.m4a",
        downloaded_bytes=123,
        format_downloaded="audio",
        downloaded_at=_now(),
    )
    db_session.add(download)
    db_session.commit()
    return download


# ---------- profile scope ----------

def test_download_profile_worker_runs_after_show_indexing():
    from task_manager.tasks.workers.download_profile_worker import download_profile_worker

    event_names = {
        trigger.event_name
        for trigger in download_profile_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }
    assert "show.indexed" in event_names
    assert "show.added" not in event_names


def test_podcast_profile_filters_by_type_status_and_countdown(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = _now()
    final_ep = _make_episode(db_session, show, season, slug="final", ep_id="ep.1", status="published_final", published_at=now, index=1)
    countdown_ep = _make_episode(db_session, show, season, slug="countdown", ep_id="ep.2", status="published_with_countdown", published_at=now, index=2)
    _make_episode(db_session, show, season, slug="live", ep_id="ep.3", status="live", published_at=now, index=3)
    _make_episode(db_session, show, season, slug="trailer", ep_id="trailer.1", status="published_final", published_at=now, index=4)
    profile = _make_podcast_profile(db_session, show, lmp)

    assert {e.slug for e in get_download_profile_episodes(db_session, profile)} == {final_ep.slug}
    profile.download_with_countdown = True
    assert {e.slug for e in get_download_profile_episodes(db_session, profile)} == {final_ep.slug, countdown_ep.slug}


def test_podcast_profile_respects_days_in_past_window(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = _now()
    recent = _make_episode(db_session, show, season, slug="recent", ep_id="ep.1", status="published_final", published_at=now - timedelta(days=1), index=1)
    _make_episode(db_session, show, season, slug="old", ep_id="ep.2", status="published_final", published_at=now - timedelta(days=30), index=2)
    profile = _make_podcast_profile(db_session, show, lmp, download_days_in_past=7)

    assert [episode.slug for episode in get_download_profile_episodes(db_session, profile)] == [recent.slug]


def test_series_profile_filters_by_seasons_and_upcoming(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season1 = _make_season(db_session, show, index=1, slug="s1")
    season2 = _make_season(db_session, show, index=2, slug="s2")
    lmp = _make_local_media_profile(db_session)
    now = _now()
    ep1 = _make_episode(db_session, show, season1, slug="ep1", ep_id="ep.1", status="published_final", published_at=now, index=1)
    ep2 = _make_episode(db_session, show, season2, slug="ep2", ep_id="ep.2", status="published_final", published_at=now, index=2)
    profile = _make_series_profile(db_session, show, lmp, [season1])

    assert {e.slug for e in get_download_profile_episodes(db_session, profile)} == {ep1.slug}
    profile.include_upcoming_seasons = True
    assert {e.slug for e in get_download_profile_episodes(db_session, profile)} == {ep1.slug, ep2.slug}


# ---------- persistent artifact reconciliation ----------

def test_ensure_episode_download_creates_absent_artifact(db_session):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=_now(), index=1)
    profile = _make_podcast_profile(db_session, show, lmp)

    action = ensure_episode_download(db_session, profile, episode)
    db_session.commit()

    row = db_session.get(EpisodeMediaDownload, action.media_download_id)
    assert action.needs_operation is True
    assert action.is_redownload is False
    assert row.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
    assert row.download_profile_id == profile.id
    assert not hasattr(row, "download_status")
    assert not hasattr(row, "progress")


def test_ensure_episode_download_adopts_available_manual_artifact(db_session):
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=_now(), index=1)
    profile = _make_podcast_profile(db_session, show, lmp)
    manual = _completed_download(db_session, episode, lmp, profile)
    manual.download_profile_id = None
    db_session.commit()

    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download
    action = ensure_episode_download(db_session, profile, episode)

    assert action.needs_operation is False
    assert manual.download_profile_id == profile.id


def test_ensure_episode_download_respects_user_retry_suppression(db_session):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=_now(), index=1)
    profile = _make_podcast_profile(db_session, show, lmp)
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=lmp.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        automatic_retry_suppressed=True,
        file_path="/downloads/cancelled.m4a",
    )
    db_session.add(download)
    db_session.commit()

    action = ensure_episode_download(db_session, profile, episode)
    assert action.needs_operation is False
    assert download.automatic_retry_suppressed is True


def test_ensure_episode_download_redownloads_countdown_artifact_when_final(db_session):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=_now(), index=1)
    profile = _make_podcast_profile(db_session, show, lmp, download_with_countdown=True, redownload_final=True)
    existing = _completed_download(db_session, episode, lmp, profile, publish_status="published_with_countdown")

    action = ensure_episode_download(db_session, profile, episode)

    assert action.needs_operation is True
    assert action.is_redownload is True
    assert existing.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
    assert existing.downloaded_publish_status is None


@pytest.mark.parametrize("artifact_status", ["missing", "corrupted"])
def test_ensure_episode_download_rearms_unhealthy_artifact(db_session, artifact_status):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=_now(), index=1)
    profile = _make_podcast_profile(db_session, show, lmp)
    existing = _completed_download(db_session, episode, lmp, profile)
    existing.artifact_status = artifact_status
    existing.artifact_error = "file watcher"
    db_session.commit()

    action = ensure_episode_download(db_session, profile, episode)

    assert action.needs_operation is True
    assert action.is_redownload is False
    assert existing.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
    assert existing.artifact_error is None
    assert existing.downloaded_bytes is None


# ---------- cleanup ----------

def test_cleanup_older_episodes_deletes_domain_row_and_file(db_session, tmp_path):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from task_manager.tasks.workers.download_profile_worker._helpers import cleanup_older_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = _now()
    old_episode = _make_episode(db_session, show, season, slug="old", ep_id="ep.1", status="published_final", published_at=now - timedelta(days=30), index=1)
    recent_episode = _make_episode(db_session, show, season, slug="recent", ep_id="ep.2", status="published_final", published_at=now - timedelta(days=1), index=2)
    profile = _make_podcast_profile(db_session, show, lmp, download_days_in_past=7, delete_older_episodes=True)

    old_file = tmp_path / "old.m4a"
    recent_file = tmp_path / "recent.m4a"
    old_file.write_bytes(b"data")
    recent_file.write_bytes(b"data")
    rows = [
        EpisodeMediaDownload(
            type=MediaType.EPISODE.value,
            media_item_id=episode.id,
            local_media_profile_id=lmp.id,
            download_profile_id=profile.id,
            artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
            file_path=str(path),
        )
        for episode, path in [(old_episode, old_file), (recent_episode, recent_file)]
    ]
    db_session.add_all(rows)
    db_session.commit()

    assert cleanup_older_episodes(db_session, profile) == 1
    db_session.commit()
    assert not old_file.exists()
    assert recent_file.exists()
    assert [row.media_item_id for row in db_session.query(EpisodeMediaDownload).all()] == [recent_episode.id]


# ---------- worker integration with universal operations ----------

def test_run_worker_creates_system_media_download_operation(db_session, monkeypatch):
    from task_manager.tasks.workers.download_profile_worker import service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=_now(), index=1)
    _make_podcast_profile(db_session, show, lmp)
    db_session.commit()

    created = Mock(return_value=SimpleNamespace(id="op-1"))
    dispatched = Mock(return_value=1)
    monkeypatch.setattr(service, "create_media_download_operation", created)
    monkeypatch.setattr(service, "dispatch_queued_media_download_operations", dispatched)

    asyncio.run(service.run_download_profile_worker(db_session, resource_id=episode.id, resource_type="episode"))

    created.assert_called_once()
    _, kwargs = created.call_args
    assert kwargs["source"] == "SYSTEM"
    assert kwargs["is_redownload"] is False
    dispatched.assert_called_once()


def test_run_worker_no_enabled_profiles_is_a_noop(db_session, monkeypatch):
    from task_manager.tasks.workers.download_profile_worker import service

    created = Mock()
    dispatched = Mock()
    monkeypatch.setattr(service, "create_media_download_operation", created)
    monkeypatch.setattr(service, "dispatch_queued_media_download_operations", dispatched)

    asyncio.run(service.run_download_profile_worker(db_session, resource_id=0, resource_type="download_profile"))

    created.assert_not_called()
    dispatched.assert_not_called()
