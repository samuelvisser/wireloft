from __future__ import annotations

import asyncio
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


def _library(
    session: Session,
    tmp_path: Path,
    *,
    output_template: str = "/downloads/{{ show }}/{{ episode_identifier }}.ext",
):
    from backend.db.models import Episode, LocalMediaProfile, PodcastDownloadProfile, Season, Show
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
        index=2,
        episode_identifier="ep.2",
        slug="episode-2",
        title="Episode 2",
        description=None,
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/episode-2",
    )
    local_profile = LocalMediaProfile(
        slug="audio",
        name="Audio",
        output_template=output_template,
        preferred_format="format_audio_only",
    )
    download_profile = PodcastDownloadProfile(
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
    session.add_all([show, season, episode, local_profile, download_profile])
    session.flush()

    old_path = tmp_path / "legacy" / "episode.m4a"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"media")
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=local_profile.id,
        download_profile=download_profile,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(old_path),
    )
    session.add(download)
    session.commit()
    return show, episode, local_profile, download_profile, download, old_path


def test_rename_file_worker_moves_artifact_and_updates_path(monkeypatch, tmp_path):
    from config import get_settings
    from task_manager.tasks.workers.rename_file_worker.service import run_rename_file_worker

    session, engine = _session()
    try:
        monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
        _show, episode, _local_profile, _download_profile, download, old_path = _library(session, tmp_path)

        result = asyncio.run(run_rename_file_worker(session, episode_id=episode.id))

        expected = (tmp_path / "test-show" / "ep.2.m4a").resolve()
        session.refresh(download)
        assert result.data["files_renamed"] == 1
        assert result.data["files_recovered"] == 0
        assert download.file_path == str(expected)
        assert expected.read_bytes() == b"media"
        assert not old_path.exists()
    finally:
        session.close()
        engine.dispose()


def test_rename_file_worker_recovers_move_completed_before_database_commit(monkeypatch, tmp_path):
    from config import get_settings
    from task_manager.tasks.workers.rename_file_worker.service import run_rename_file_worker

    session, engine = _session()
    try:
        monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
        _show, episode, _local_profile, _download_profile, download, old_path = _library(session, tmp_path)
        expected = (tmp_path / "test-show" / "ep.2.m4a").resolve()
        expected.parent.mkdir(parents=True)
        old_path.replace(expected)

        result = asyncio.run(run_rename_file_worker(session, episode_id=episode.id))

        session.refresh(download)
        assert result.data["files_recovered"] == 1
        assert result.data["files_renamed"] == 0
        assert download.file_path == str(expected)
        assert expected.read_bytes() == b"media"
    finally:
        session.close()
        engine.dispose()


def test_identifier_event_scope_skips_templates_not_derived_from_identifier(monkeypatch, tmp_path):
    from config import get_settings
    from task_manager.tasks.workers.rename_file_worker.service import run_rename_file_worker

    session, engine = _session()
    try:
        monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
        _show, episode, _local_profile, _download_profile, download, old_path = _library(
            session,
            tmp_path,
            output_template="/downloads/{{ show }}/{{ episode }}.ext",
        )

        result = asyncio.run(run_rename_file_worker(
            session,
            episode_id=episode.id,
            identifier_fields_only=True,
        ))

        session.refresh(download)
        assert result.data["files_considered"] == 0
        assert download.file_path == str(old_path)
        assert old_path.exists()
    finally:
        session.close()
        engine.dispose()


def test_show_file_rename_operation_targets_selected_profile(tmp_path):
    from backend.api.endpoints.shows import service
    from task_manager.scheduler.db import TaskOperationTarget

    session, engine = _session()
    try:
        show, episode, _local_profile, download_profile, _download, _old_path = _library(session, tmp_path)

        result = service.request_show_file_rename(session, show.slug, download_profile.id)

        assert result["queued"] is True
        assert result["episodes_queued"] == 1
        assert result["download_profiles_queued"] == 1
        target = session.query(TaskOperationTarget).filter_by(operation_id=result["operation_id"]).one()
        assert target.task_key == "rename_file_worker"
        assert target.resource_type == "episode"
        assert target.resource_id == episode.id
        assert target.task_kwargs == {"download_profile_id": download_profile.id}

        with pytest.raises(HTTPException) as exc:
            service.request_show_file_rename(session, show.slug, 999999)
        assert exc.value.status_code == 422
    finally:
        session.close()
        engine.dispose()


def test_local_media_profile_rename_operation_targets_affected_episodes(tmp_path):
    from backend.api.endpoints.local_media_profiles import service
    from task_manager.scheduler.db import TaskOperationTarget

    session, engine = _session()
    try:
        _show, episode, local_profile, _download_profile, _download, _old_path = _library(session, tmp_path)

        result = service.request_local_media_profile_file_rename(session, local_profile.slug)

        assert result["queued"] is True
        assert result["episodes_queued"] == 1
        target = session.query(TaskOperationTarget).filter_by(operation_id=result["operation_id"]).one()
        assert target.task_key == "rename_file_worker"
        assert target.resource_id == episode.id
        assert target.task_kwargs == {"local_media_profile_id": local_profile.id}
    finally:
        session.close()
        engine.dispose()


def test_rename_file_worker_registers_identifier_change_event():
    from task_manager.tasks.helpers.episodes.events import EPISODE_IDENTIFIER_CHANGED_EVENT
    from task_manager.tasks.workers.rename_file_worker import rename_file_worker

    event_names = {
        trigger.event_name
        for trigger in rename_file_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }
    assert EPISODE_IDENTIFIER_CHANGED_EVENT in event_names
    assert rename_file_worker._task_meta.default_max_retries == 2
    assert rename_file_worker._task_meta.tracks_progress is True
