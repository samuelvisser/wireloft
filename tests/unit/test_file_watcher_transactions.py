from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import Session


def _db_with_download(tmp_path: Path):
    from backend.db import Base
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.artifact_identity import inspect_artifact
    from backend.utils.helpers import generate_uuid

    database_path = tmp_path / "file-watcher-transactions.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session = Session(engine)

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
    season = Season(show=show, index=1, slug="season-2026", name="2026")
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.101",
        slug="test-episode-101",
        title="Ep. 101",
        description=None,
        duration=100.0,
        publish_status="published_final",
        sharing_url="https://example.test/ep",
    )
    profile = LocalMediaProfile(
        slug="audio",
        name="Audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    session.add_all([show, season, episode, profile])
    session.commit()

    file_path = tmp_path / "episode.m4a"
    file_path.write_bytes(b"hello world")
    identity = inspect_artifact(file_path)
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(file_path),
        downloaded_bytes=identity.size_bytes,
        artifact_stat_dev=identity.stat_dev,
        artifact_stat_ino=identity.stat_ino,
        artifact_size_bytes=identity.size_bytes,
        artifact_fingerprint=identity.fingerprint,
    )
    session.add(download)
    session.commit()
    download_id = download.id
    session.commit()

    return session, engine, download_id, file_path


@pytest.fixture(autouse=True)
def _enable_file_watcher(monkeypatch: pytest.MonkeyPatch):
    from config import get_settings

    monkeypatch.setattr(get_settings().file_watcher, "enabled", True)
    monkeypatch.setattr(get_settings().file_watcher, "verify_file_size", True)
    yield


def test_filesystem_checks_use_detached_models_without_database_transaction(tmp_path, monkeypatch):
    from backend.db.models.media_download import MediaDownloadBase
    from task_manager.tasks.workers.file_watcher import service

    session, engine, _download_id, _file_path = _db_with_download(tmp_path)
    original_reconcile = service._reconcile
    checked = False

    def reconcile_without_transaction(download, *, verify_file_size):
        nonlocal checked
        checked = True
        assert isinstance(download, MediaDownloadBase)
        assert sa_inspect(download).detached
        assert not session.in_transaction()
        return original_reconcile(download, verify_file_size=verify_file_size)

    monkeypatch.setattr(service, "_reconcile", reconcile_without_transaction)

    asyncio.run(service.run_file_watcher(session))

    assert checked
    assert not session.in_transaction()

    session.close()
    engine.dispose()


def test_stale_filesystem_result_does_not_overwrite_newer_download(tmp_path, monkeypatch):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.utils.artifact_identity import inspect_artifact
    from task_manager.tasks.workers.file_watcher import service

    session, engine, download_id, file_path = _db_with_download(tmp_path)
    os.remove(file_path)
    original_reconcile = service._reconcile
    replacement_path = tmp_path / "replacement.m4a"

    def reconcile_while_download_changes(download, *, verify_file_size):
        updates = original_reconcile(download, verify_file_size=verify_file_size)
        assert updates["artifact_status"] == MediaDownloadArtifactStatus.MISSING.value
        assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
        assert sa_inspect(download).detached
        assert not session.in_transaction()

        replacement_path.write_bytes(b"newer completed download")
        replacement_identity = inspect_artifact(replacement_path)
        with Session(engine) as concurrent_session:
            current = concurrent_session.get(EpisodeMediaDownload, download_id)
            assert current is not None
            current.file_path = str(replacement_path)
            current.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
            current.artifact_error = None
            current.downloaded_bytes = replacement_identity.size_bytes
            current.artifact_stat_dev = replacement_identity.stat_dev
            current.artifact_stat_ino = replacement_identity.stat_ino
            current.artifact_size_bytes = replacement_identity.size_bytes
            current.artifact_fingerprint = replacement_identity.fingerprint
            concurrent_session.commit()

        return updates

    monkeypatch.setattr(service, "_reconcile", reconcile_while_download_changes)

    asyncio.run(service.run_file_watcher(session))

    with Session(engine) as verify_session:
        current = verify_session.get(EpisodeMediaDownload, download_id)
        assert current is not None
        assert current.file_path == str(replacement_path)
        assert current.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
        assert current.artifact_error is None

    session.close()
    engine.dispose()
