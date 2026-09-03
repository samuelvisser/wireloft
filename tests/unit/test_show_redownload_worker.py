from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def _library(session: Session, tmp_path: Path):
    from backend.db.models import Episode, LocalMediaProfile, PodcastDownloadProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import EpIdType, MediaDownloadStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid="show-uuid",
        slug="test-show",
        title="Test Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    episode = Episode(
        uuid="episode-uuid",
        type=MediaType.EPISODE.value,
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="episode-1",
        title="Episode 1",
        description=None,
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/episode-1",
        published_date=datetime(2026, 9, 1, 12, 0, 0),
    )
    local_profile = LocalMediaProfile(
        slug="audio",
        name="Audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    profile = PodcastDownloadProfile(
        show=show,
        local_media_profile=local_profile,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=0,
        delete_older_episodes=False,
    )
    old_path = tmp_path / "old" / "episode-1.m4a"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"old")
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=local_profile.id,
        download_profile=profile,
        download_status=MediaDownloadStatus.DOWNLOADED.value,
        file_path=str(old_path),
        progress=100,
        downloaded_bytes=3,
        format_downloaded="audio",
        downloaded_publish_status="published_final",
        is_redownload_attempt=False,
    )
    session.add_all([show, season, episode, local_profile, profile])
    session.flush()
    download.media_item_id = episode.id
    download.local_media_profile_id = local_profile.id
    session.add(download)
    session.commit()
    return show, episode, profile, download, old_path


def test_show_redownload_request_targets_one_or_all_profiles(monkeypatch, tmp_path):
    from backend.api.endpoints.shows import service
    from backend.db.models import LocalMediaProfile, PodcastDownloadProfile
    from backend.types.download_profile_types import EpIdType

    session, engine = _session()
    show, _episode, profile, _download, _old_path = _library(session, tmp_path)
    second_local = LocalMediaProfile(
        slug="video",
        name="Video",
        output_template="/downloads/{{ show }}/video/{{ episode }}.ext",
        preferred_format="format_1080p",
    )
    second_profile = PodcastDownloadProfile(
        show=show,
        local_media_profile=second_local,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=0,
        delete_older_episodes=False,
    )
    session.add_all([second_local, second_profile])
    session.commit()

    queued: list[tuple[str, dict]] = []
    request_uuid = UUID("12345678-1234-5678-1234-567812345678")
    monkeypatch.setattr(service, "uuid4", lambda: request_uuid)
    monkeypatch.setattr(service, "queue_event", lambda _s, name, data: queued.append((name, data)))

    result = service.request_show_episode_redownload(session, show.slug, None)
    assert result == {
        "queued": True,
        "download_profiles_queued": 2,
        "request_id": str(request_uuid),
    }
    assert queued[-1][1]["download_profile_id"] is None
    assert queued[-1][1]["manual_request_id"] == str(request_uuid)

    result = service.request_show_episode_redownload(session, show.slug, profile.id)
    assert result["download_profiles_queued"] == 1
    assert queued[-1][1]["download_profile_id"] == profile.id

    with pytest.raises(HTTPException) as exc:
        service.request_show_episode_redownload(session, show.slug, 999999)
    assert exc.value.status_code == 422

    session.close()
    engine.dispose()


def test_redownload_worker_replaces_existing_file_and_generation(monkeypatch, tmp_path):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    from config import get_settings
    from task_manager.tasks.workers.redownload_show_episodes_worker import service

    session, engine = _session()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    _show, episode, profile, download, old_path = _library(session, tmp_path)
    original_generation = download.attempt_generation

    targets = service._target_episode_profiles(session, [profile])
    prepared = service._prepare_redownloads(session, targets)

    assert len(prepared) == 1
    session.expire_all()
    refreshed = session.get(EpisodeMediaDownload, download.id)
    assert refreshed is not None
    assert refreshed.attempt_generation == original_generation + 1
    assert refreshed.download_status == MediaDownloadStatus.PENDING.value
    assert refreshed.progress == 0
    assert refreshed.downloaded_bytes is None
    assert refreshed.format_downloaded is None
    assert refreshed.downloaded_publish_status is None
    assert refreshed.is_redownload_attempt is True
    assert refreshed.download_profile_id == profile.id
    assert refreshed.file_path == str((tmp_path / "test-show" / "episode-1.ext").resolve())
    assert not old_path.exists()

    session.close()
    engine.dispose()


def test_redownload_worker_registers_show_event():
    from backend.api.endpoints.shows.service import SHOW_REDOWNLOAD_EPISODES_REQUESTED_EVENT
    from task_manager.tasks.workers.redownload_show_episodes_worker import redownload_show_episodes_worker

    event_names = {
        trigger.event_name
        for trigger in redownload_show_episodes_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }
    assert SHOW_REDOWNLOAD_EPISODES_REQUESTED_EVENT in event_names
    assert redownload_show_episodes_worker._task_meta.default_max_retries == 0
