from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
        description="",
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
        description="",
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/episode-1",
        published_date=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
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
    video_path.write_bytes(b"video" * 3)

    audio_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=audio_profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(audio_path),
        downloaded_bytes=5,
        format_downloaded="audio",
        downloaded_at=datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc),
        downloaded_publish_status="published_final",
    )
    video_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=video_profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(video_path),
        downloaded_bytes=15,
        format_downloaded="video",
        downloaded_at=datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc),
        downloaded_publish_status="published_final",
    )
    session.add_all([audio_download, video_download])
    session.commit()
    return (
        show,
        audio_profile,
        video_profile,
        unused_profile,
        audio_download,
        video_download,
    )


def _disable_dispatch(monkeypatch):
    monkeypatch.setattr(
        "task_manager.tasks.media_download_operations.dispatch_queued_media_download_operations",
        lambda _session: 0,
    )


def test_show_redownload_uses_independent_download_operation_dependencies(monkeypatch, tmp_path):
    from backend.api.endpoints.shows import service
    from task_manager.scheduler.db import TaskOperation, TaskOperationDependency
    from task_manager.scheduler.types import (
        OperationDependencyCancelPolicy,
        OperationSource,
    )

    session, engine = _session()
    try:
        _disable_dispatch(monkeypatch)
        (
            show,
            _audio_profile,
            _video_profile,
            _unused_profile,
            audio_download,
            video_download,
        ) = _library(session, tmp_path)

        result = service.request_show_episode_redownload(session, show.slug, None)
        parent = session.get(TaskOperation, result["operation_id"])
        assert parent is not None
        assert parent.kind == "show.redownload_episodes"
        assert parent.targets == []

        dependencies = (
            session.query(TaskOperationDependency)
            .filter_by(parent_operation_id=parent.id)
            .order_by(TaskOperationDependency.id)
            .all()
        )
        assert [dependency.context["media_download_id"] for dependency in dependencies] == [
            audio_download.id,
            video_download.id,
        ]
        assert [dependency.weight for dependency in dependencies] == [5.0, 15.0]
        assert all(
            dependency.cancel_policy
            == OperationDependencyCancelPolicy.CANCEL_IF_EXCLUSIVE.value
            for dependency in dependencies
        )

        children = [dependency.child_operation for dependency in dependencies]
        assert all(child is not None for child in children)
        assert all(child.kind == "media.download" for child in children)
        assert all(child.source == OperationSource.SYSTEM.value for child in children)
        assert [child.resource_id for child in children] == [
            audio_download.id,
            video_download.id,
        ]
        assert all(child.context["is_redownload"] is True for child in children)
        assert all(child.context["prepare_existing_artifact"] is True for child in children)
        assert all(len(child.targets) == 1 for child in children)
        assert all(
            child.targets[0].task_kwargs["prepare_existing_artifact"] is True
            for child in children
        )

        # Parent construction freezes orchestration facts but does not delete a
        # byte. Destructive replacement preparation belongs to the child worker.
        assert Path(audio_download.file_path).exists()
        assert Path(video_download.file_path).exists()
    finally:
        session.close()
        engine.dispose()


def test_show_redownload_scope_creates_only_selected_profile_dependency(monkeypatch, tmp_path):
    from backend.api.endpoints.shows import service
    from task_manager.scheduler.db import TaskOperationDependency

    session, engine = _session()
    try:
        _disable_dispatch(monkeypatch)
        (
            show,
            audio_profile,
            _video_profile,
            unused_profile,
            audio_download,
            _video_download,
        ) = _library(session, tmp_path)

        result = service.request_show_episode_redownload(
            session,
            show.slug,
            audio_profile.id,
        )
        dependencies = session.query(TaskOperationDependency).filter_by(
            parent_operation_id=result["operation_id"],
        ).all()

        assert result["local_media_profiles_queued"] == 1
        assert len(dependencies) == 1
        assert dependencies[0].context["media_download_id"] == audio_download.id

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


def test_bulk_redownload_selects_only_episodes_older_than_latest_download_limit(monkeypatch, tmp_path):
    from datetime import timedelta

    from backend.api.endpoints.shows import service
    from backend.db.models import Episode, Season
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from task_manager.scheduler.db import TaskOperationDependency

    session, engine = _session()
    try:
        _disable_dispatch(monkeypatch)
        (
            show,
            audio_profile,
            _video_profile,
            _unused_profile,
            original_audio,
            original_video,
        ) = _library(session, tmp_path)
        first_episode = session.get(Episode, original_audio.media_item_id)
        first_episode.published_date = datetime.now(timezone.utc) - timedelta(days=100)
        season = session.query(Season).filter_by(show_id=show.id).one()

        def add_episode(index: int, days_old: int, *, downloaded: bool):
            episode = Episode(
                uuid=f"retention-episode-{index}",
                type=MediaType.EPISODE.value,
                show=show,
                season=season,
                index=index,
                episode_identifier=f"ep.{index}",
                slug=f"retention-episode-{index}",
                title=f"Retention episode {index}",
                description="",
                duration=60,
                publish_status="published_final",
                sharing_url=f"https://example.test/retention-episode-{index}",
                published_date=datetime.now(timezone.utc) - timedelta(days=days_old),
            )
            session.add(episode)
            session.flush()
            if not downloaded:
                return None
            path = tmp_path / f"episode-{index}.mp3"
            path.write_bytes(b"audio")
            download = EpisodeMediaDownload(
                type=MediaType.EPISODE.value,
                media_item_id=episode.id,
                local_media_profile_id=audio_profile.id,
                artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
                file_path=str(path),
                downloaded_bytes=5,
            )
            session.add(download)
            session.flush()
            return download

        middle = add_episode(2, 40, downloaded=True)
        newest_downloaded = add_episode(3, 2, downloaded=True)
        add_episode(4, 0, downloaded=False)
        result = service.request_show_episode_redownload(
            session,
            show.slug,
            None,
            delete_older_than="latest_downloads",
            delete_older_than_latest_downloads=2,
        )
        dependencies = session.query(TaskOperationDependency).filter_by(
            parent_operation_id=result["operation_id"],
        ).all()
        selected_ids = {
            dependency.context["media_download_id"] for dependency in dependencies
        }
        assert selected_ids == {original_audio.id, original_video.id}
        assert middle.id not in selected_ids
        assert newest_downloaded.id not in selected_ids

        # Every actual download fits within the limit. The undownloaded
        # newest episode must not cause any file to be re-downloaded.
        with pytest.raises(HTTPException) as exc:
            service.request_show_episode_redownload(
                session,
                show.slug,
                None,
                delete_older_than="latest_downloads",
                delete_older_than_latest_downloads=4,
            )
        assert exc.value.status_code == 422

        # Days are based on episode publication dates and use the same
        # selection logic for both maintenance actions.
        days_result = service.request_show_episode_redownload(
            session,
            show.slug,
            None,
            delete_older_than="days",
            delete_older_than_days=50,
        )
        day_dependencies = session.query(TaskOperationDependency).filter_by(
            parent_operation_id=days_result["operation_id"],
        ).all()
        assert {
            dependency.context["media_download_id"] for dependency in day_dependencies
        } == {original_audio.id, original_video.id}
    finally:
        session.close()
        engine.dispose()


def test_bulk_redownload_without_older_downloads_does_not_touch_recent_files(monkeypatch, tmp_path):
    from datetime import timedelta

    from backend.api.endpoints.shows import service
    from backend.db.models import Episode
    from task_manager.scheduler.db import TaskOperationDependency

    session, engine = _session()
    try:
        _disable_dispatch(monkeypatch)
        (
            show,
            _audio_profile,
            _video_profile,
            _unused_profile,
            original_audio,
            _original_video,
        ) = _library(session, tmp_path)
        episode = session.get(Episode, original_audio.media_item_id)
        episode.published_date = datetime.now(timezone.utc) - timedelta(days=2)

        with pytest.raises(HTTPException) as exc:
            service.request_show_episode_redownload(
                session,
                show.slug,
                None,
                delete_older_than="days",
                delete_older_than_days=90,
            )
        assert exc.value.status_code == 422
        assert session.query(TaskOperationDependency).all() == []
    finally:
        session.close()
        engine.dispose()
