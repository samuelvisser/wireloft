from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def _library(session: Session, tmp_path: Path):
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
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
    audio_profile = LocalMediaProfile(
        slug="audio",
        name="Audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    video_profile = LocalMediaProfile(
        slug="video",
        name="Video",
        output_template="/downloads/{{ show }}/video/{{ episode }}.ext",
        preferred_format="format_1080p",
    )
    unused_profile = LocalMediaProfile(
        slug="unused",
        name="Unused",
        output_template="/downloads/{{ show }}/unused/{{ episode }}.ext",
        preferred_format="format_720p",
    )
    session.add_all([show, season, episode, audio_profile, video_profile, unused_profile])
    session.flush()

    audio_path = tmp_path / "old" / "episode-1.m4a"
    video_path = tmp_path / "old" / "episode-1.mp4"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"audio")
    video_path.write_bytes(b"video")

    audio_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=audio_profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(audio_path),
        downloaded_bytes=5,
        format_downloaded="audio",
        downloaded_at=datetime(2026, 9, 2, 12, 0, 0),
        downloaded_publish_status="published_final",
    )
    video_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=video_profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(video_path),
        downloaded_bytes=5,
        format_downloaded="video",
        downloaded_at=datetime(2026, 9, 2, 12, 0, 0),
        downloaded_publish_status="published_final",
    )
    session.add_all([audio_download, video_download])
    session.commit()
    return (
        show,
        episode,
        audio_profile,
        video_profile,
        unused_profile,
        audio_download,
        video_download,
        audio_path,
    )


def test_show_redownload_request_uses_existing_local_media_profiles(tmp_path):
    from backend.api.endpoints.shows import service
    from backend.db.models import DownloadProfileBase
    from task_manager.scheduler.db import TaskOperationTarget

    session, engine = _session()
    try:
        (
            show,
            _episode,
            audio_profile,
            _video_profile,
            unused_profile,
            _audio_download,
            _video_download,
            _audio_path,
        ) = _library(session, tmp_path)

        # These rows are intentionally manual: no Download Profile exists at all.
        assert session.query(DownloadProfileBase).count() == 0

        result = service.request_show_episode_redownload(session, show.slug, None)
        assert result["queued"] is True
        assert result["local_media_profiles_queued"] == 2
        UUID(str(result["operation_id"]))

        all_target = session.query(TaskOperationTarget).filter_by(
            operation_id=result["operation_id"]
        ).one()
        assert all_target.task_key == "redownload_show_episodes_worker"
        assert all_target.task_kwargs == {"local_media_profile_id": None}

        selected = service.request_show_episode_redownload(
            session,
            show.slug,
            audio_profile.id,
        )
        assert selected["local_media_profiles_queued"] == 1
        selected_target = session.query(TaskOperationTarget).filter_by(
            operation_id=selected["operation_id"]
        ).one()
        assert selected_target.task_kwargs == {
            "local_media_profile_id": audio_profile.id,
        }

        with pytest.raises(HTTPException) as exc:
            service.request_show_episode_redownload(
                session,
                show.slug,
                unused_profile.id,
            )
        assert exc.value.status_code == 422
    finally:
        session.close()
        engine.dispose()


def test_redownload_worker_preserves_manual_download_provenance(monkeypatch, tmp_path):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from config import get_settings
    from task_manager.scheduler.db import TaskOperation
    from task_manager.tasks.workers.redownload_show_episodes_worker import _helpers

    session, engine = _session()
    try:
        monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
        monkeypatch.setattr(
            _helpers,
            "dispatch_queued_media_download_operations",
            lambda _session: 0,
        )
        (
            _show,
            _episode,
            _audio_profile,
            _video_profile,
            _unused_profile,
            audio_download,
            _video_download,
            audio_path,
        ) = _library(session, tmp_path)

        assert audio_download.download_profile_id is None
        prepared = _helpers._prepare_redownloads(session, [audio_download])

        assert len(prepared) == 1
        session.expire_all()
        refreshed = session.get(EpisodeMediaDownload, audio_download.id)
        assert refreshed is not None
        assert refreshed.download_profile_id is None
        assert refreshed.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
        assert refreshed.downloaded_bytes is None
        assert refreshed.format_downloaded is None
        assert refreshed.downloaded_at is None
        assert refreshed.downloaded_publish_status is None
        assert refreshed.file_path == str((tmp_path / "test-show" / "episode-1.ext").resolve())
        assert not audio_path.exists()

        operation = session.get(TaskOperation, prepared[0].operation_id)
        assert operation is not None
        assert operation.context["local_media_profile_id"] == refreshed.local_media_profile_id
        assert operation.context["is_redownload"] is True
    finally:
        session.close()
        engine.dispose()


def test_redownload_worker_targets_existing_media_rows(monkeypatch, tmp_path):
    from task_manager.tasks.workers.redownload_show_episodes_worker import service

    session, engine = _session()
    try:
        (
            show,
            _episode,
            audio_profile,
            _video_profile,
            _unused_profile,
            audio_download,
            _video_download,
            _audio_path,
        ) = _library(session, tmp_path)
        prepared_inputs: list[list[object]] = []

        async def no_sleep(_seconds):
            return None

        monkeypatch.setattr(service.asyncio, "sleep", no_sleep)

        def prepare(_session, downloads):
            prepared_inputs.append(list(downloads))
            return [SimpleNamespace(operation_id="operation-1")]

        monkeypatch.setattr(service, "_prepare_redownloads", prepare)
        monkeypatch.setattr(service, "_check_targets", lambda *_args: (1, 100, None))

        result = asyncio.run(
            service.run_redownload_show_episodes_worker(
                session,
                show_id=show.id,
                local_media_profile_id=audio_profile.id,
            )
        )

        assert [[download.id for download in group] for group in prepared_inputs] == [
            [audio_download.id]
        ]
        assert result["episode_files"] == 1
        assert result["local_media_profiles"] == 1
    finally:
        session.close()
        engine.dispose()


def test_redownload_worker_is_not_automatically_retried():
    from task_manager.tasks.workers.redownload_show_episodes_worker import redownload_show_episodes_worker

    assert redownload_show_episodes_worker._task_meta.default_max_retries == 0
