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
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def _library(session: Session, tmp_path: Path):
    from backend.db.models import (
        Episode,
        LocalMediaProfile,
        PodcastDownloadProfile,
        Season,
        Show,
    )
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import EpIdType, MediaDownloadArtifactStatus
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

    def add_download_profile(local_media_profile):
        profile = PodcastDownloadProfile(
            show_id=show.id,
            local_media_profile_id=local_media_profile.id,
            enable_profile=True,
            ep_id_type_list=[EpIdType.EP.value],
            download_with_countdown=False,
            redownload_final=False,
            download_days_in_past=0,
            download_episode_count=0,
            delete_older_episodes=False,
        )
        session.add(profile)
        session.flush()
        return profile

    audio_download_profile = add_download_profile(audio_profile)
    video_download_profile = add_download_profile(video_profile)
    unused_download_profile = add_download_profile(unused_profile)

    audio_path = tmp_path / "old" / "episode-1.m4a"
    video_path = tmp_path / "old" / "episode-1.mp4"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"audio")
    video_path.write_bytes(b"video")

    audio_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=audio_profile.id,
        download_profile_id=audio_download_profile.id,
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
        download_profile_id=video_download_profile.id,
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
        audio_profile,
        unused_profile,
        (audio_download_profile, video_download_profile, unused_download_profile),
        audio_download,
        video_download,
        audio_path,
        video_path,
    )


def test_show_delete_downloads_request_uses_existing_local_media_profiles(tmp_path):
    from backend.api.endpoints.shows import service
    from task_manager.scheduler.db import TaskOperationTarget

    session, engine = _session()
    try:
        (
            show,
            audio_profile,
            unused_profile,
            _download_profiles,
            _audio_download,
            _video_download,
            _audio_path,
            _video_path,
        ) = _library(session, tmp_path)

        result = service.request_show_download_delete(session, show.slug, None)
        assert result["queued"] is True
        assert result["local_media_profiles_queued"] == 2
        UUID(str(result["operation_id"]))

        all_target = session.query(TaskOperationTarget).filter_by(
            operation_id=result["operation_id"]
        ).one()
        assert all_target.task_key == "delete_show_downloads_worker"
        assert all_target.task_kwargs == {"local_media_profile_id": None}

        selected = service.request_show_download_delete(
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
            service.request_show_download_delete(
                session,
                show.slug,
                unused_profile.id,
            )
        assert exc.value.status_code == 422
    finally:
        session.close()
        engine.dispose()


def test_delete_show_downloads_worker_disables_only_profiles_in_selected_scope_and_leaves_deleted_rows_retryable(tmp_path):
    from backend.db.models import DownloadProfileBase
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from task_manager.tasks.workers.delete_show_downloads_worker.service import (
        run_delete_show_downloads_worker,
    )

    session, engine = _session()
    try:
        (
            show,
            audio_profile,
            _unused_profile,
            download_profiles,
            audio_download,
            video_download,
            audio_path,
            video_path,
        ) = _library(session, tmp_path)

        # A previous per-download cancellation must not survive this show-level
        # deletion. Re-enabling its Download Profile should be enough to arm it.
        audio_download.automatic_retry_suppressed = True
        session.commit()

        result = run_delete_show_downloads_worker(
            session,
            show_id=show.id,
            local_media_profile_id=audio_profile.id,
        )

        assert result["episode_files"] == 1
        assert result["local_media_profiles"] == 1
        assert result["download_profiles_disabled"] == 1
        assert not audio_path.exists()
        assert video_path.exists()

        session.expire_all()
        deleted = session.get(EpisodeMediaDownload, audio_download.id)
        untouched = session.get(EpisodeMediaDownload, video_download.id)
        assert deleted is not None
        assert deleted.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
        assert deleted.automatic_retry_suppressed is False
        assert deleted.downloaded_bytes is None
        assert deleted.format_downloaded is None
        assert deleted.downloaded_at is None
        assert deleted.downloaded_publish_status is None
        assert untouched is not None
        assert untouched.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value

        audio_download_profile, video_download_profile, unused_download_profile = download_profiles
        audio_profile_state = session.get(DownloadProfileBase, audio_download_profile.id)
        video_profile_state = session.get(DownloadProfileBase, video_download_profile.id)
        unused_profile_state = session.get(DownloadProfileBase, unused_download_profile.id)
        assert audio_profile_state is not None and audio_profile_state.enable_profile is False
        assert video_profile_state is not None and video_profile_state.enable_profile is True
        assert unused_profile_state is not None and unused_profile_state.enable_profile is True
    finally:
        session.close()
        engine.dispose()


def test_delete_show_downloads_worker_all_scope_disables_only_profiles_with_deleted_downloads(tmp_path):
    from backend.db.models import DownloadProfileBase
    from task_manager.tasks.workers.delete_show_downloads_worker.service import (
        run_delete_show_downloads_worker,
    )

    session, engine = _session()
    try:
        (
            show,
            _audio_profile,
            _unused_profile,
            download_profiles,
            _audio_download,
            _video_download,
            audio_path,
            video_path,
        ) = _library(session, tmp_path)

        result = run_delete_show_downloads_worker(session, show_id=show.id)

        assert result["episode_files"] == 2
        assert result["local_media_profiles"] == 2
        assert result["download_profiles_disabled"] == 2
        assert not audio_path.exists()
        assert not video_path.exists()

        session.expire_all()
        audio_download_profile, video_download_profile, unused_download_profile = download_profiles
        audio_profile_state = session.get(DownloadProfileBase, audio_download_profile.id)
        video_profile_state = session.get(DownloadProfileBase, video_download_profile.id)
        unused_profile_state = session.get(DownloadProfileBase, unused_download_profile.id)
        assert audio_profile_state is not None and audio_profile_state.enable_profile is False
        assert video_profile_state is not None and video_profile_state.enable_profile is False
        assert unused_profile_state is not None and unused_profile_state.enable_profile is True
    finally:
        session.close()
        engine.dispose()


def test_delete_show_downloads_worker_is_not_automatically_retried():
    from task_manager.tasks.workers.delete_show_downloads_worker import (
        delete_show_downloads_worker,
    )

    assert delete_show_downloads_worker._task_meta.default_max_retries == 0
