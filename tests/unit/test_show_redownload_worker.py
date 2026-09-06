from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def _manual_download(session: Session, tmp_path: Path, *, suffix: str = "one"):
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"show-{suffix}",
        slug=f"show-{suffix}",
        title=f"Show {suffix}",
        description=None,
        sharing_url=f"https://example.test/show-{suffix}",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug=f"season-{suffix}", name="Season 1")
    episode = Episode(
        uuid=f"episode-{suffix}",
        type=MediaType.EPISODE.value,
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug=f"episode-{suffix}",
        title=f"Episode {suffix}",
        duration=60,
        publish_status="published_final",
        sharing_url=f"https://example.test/episode-{suffix}",
    )
    local_profile = LocalMediaProfile(
        slug=f"audio-{suffix}",
        name=f"Audio {suffix}",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    session.add_all([show, season, episode, local_profile])
    session.flush()

    file_path = tmp_path / "old" / f"{suffix}.m4a"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"old")
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=local_profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(file_path),
    )
    session.add(download)
    session.commit()
    assert download.download_profile_id is None
    return show, episode, local_profile, download, file_path


def test_show_redownload_request_scopes_by_local_media_profile(tmp_path):
    from backend.api.endpoints.shows import service
    from backend.db.models import LocalMediaProfile
    from task_manager.scheduler.db import TaskOperationTarget

    session, engine = _session()
    try:
        show, _episode, local_profile, _download, _file_path = _manual_download(session, tmp_path)

        result = service.request_show_episode_redownload(session, show.slug, local_profile.id)
        assert result["queued"] is True
        assert result["local_media_profiles_queued"] == 1
        target = session.query(TaskOperationTarget).filter_by(operation_id=result["operation_id"]).one()
        assert target.task_key == "redownload_show_episodes_worker"
        assert target.task_kwargs == {"local_media_profile_id": local_profile.id}

        unused = LocalMediaProfile(
            slug="unused-redownload",
            name="Unused redownload",
            output_template="/downloads/unused/{{ episode }}.ext",
            preferred_format="format_audio_only",
        )
        session.add(unused)
        session.commit()
        with pytest.raises(HTTPException) as exc:
            service.request_show_episode_redownload(session, show.slug, unused.id)
        assert exc.value.status_code == 422
    finally:
        session.close()
        engine.dispose()


def test_selected_downloads_are_show_and_local_media_profile_scoped(tmp_path):
    from task_manager.tasks.workers.redownload_show_episodes_worker import _helpers

    session, engine = _session()
    try:
        show_a, _episode_a, profile_a, download_a, _ = _manual_download(session, tmp_path, suffix="a")
        _show_b, _episode_b, _profile_b, download_b, _ = _manual_download(session, tmp_path, suffix="b")

        selected = _helpers._selected_download_ids(
            session,
            show_id=show_a.id,
            local_media_profile_id=profile_a.id,
        )
        assert selected == [download_a.id]
        assert download_b.id not in selected
    finally:
        session.close()
        engine.dispose()


def test_prepare_redownload_preserves_manual_download_origin(monkeypatch, tmp_path):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from config import get_settings
    from task_manager.tasks.workers.redownload_show_episodes_worker import _helpers

    session, engine = _session()
    try:
        monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
        _show, episode, _profile, download, old_path = _manual_download(session, tmp_path)
        monkeypatch.setattr(_helpers, "_cancel_existing_attempts", lambda _s, _ids: None)
        monkeypatch.setattr(
            _helpers,
            "create_media_download_operation",
            lambda _s, current, **_kwargs: SimpleNamespace(id=f"operation-{current.id}"),
        )
        monkeypatch.setattr(_helpers, "dispatch_queued_media_download_operations", lambda _s: 0)

        targets = _helpers._prepare_redownloads(session, [download.id])

        assert len(targets) == 1
        session.expire_all()
        refreshed = session.get(EpisodeMediaDownload, download.id)
        assert refreshed is not None
        assert refreshed.download_profile_id is None
        assert refreshed.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
        assert refreshed.file_path == str((tmp_path / "show-one" / f"{episode.slug}.ext").resolve())
        assert not old_path.exists()
    finally:
        session.close()
        engine.dispose()


def test_redownload_worker_has_no_download_profile_parameter():
    import inspect

    from task_manager.tasks.workers.redownload_show_episodes_worker import redownload_show_episodes_worker

    parameters = inspect.signature(redownload_show_episodes_worker).parameters
    assert "local_media_profile_id" in parameters
    assert "download_profile_id" not in parameters
    assert redownload_show_episodes_worker._task_meta.default_max_retries == 0
