from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def final_download(tmp_path, monkeypatch):
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid
    from config import get_settings

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(
        get_settings().download_settings,
        "automatic_episode_download_delay_minutes",
        0,
    )

    show = Show(
        uuid="countdown-show-uuid",
        slug="countdown-show",
        title="Countdown Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    episode = Episode(
        uuid=generate_uuid(),
        type=MediaType.EPISODE.value,
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="countdown-episode",
        title="Countdown Episode",
        duration=100.0,
        publish_status="published_final",
        sharing_url="https://example.test/episode",
    )
    profile = LocalMediaProfile(
        slug="countdown-audio",
        name="Countdown Audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    session.add_all([show, season, episode, profile])
    session.flush()

    path = tmp_path / "countdown.m4a"
    path.write_bytes(b"countdown media")
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        downloaded_publish_status="published_with_countdown",
        redownload_when_final=True,
        file_path=str(path),
    )
    session.add(download)
    session.commit()

    yield session, episode, download

    session.close()
    engine.dispose()


def test_finalizer_listens_for_final_publication_and_startup():
    from task_manager.tasks.workers.finalize_countdown_downloads import finalize_countdown_downloads

    event_names = {
        trigger.event_name
        for trigger in finalize_countdown_downloads._task_meta.triggers
        if trigger.trigger_type == "event"
    }
    assert event_names == {"app.startup", "episode.published_final"}


def test_final_publication_queues_replacement(final_download, monkeypatch):
    from task_manager.tasks.workers.finalize_countdown_downloads import service

    session, episode, download = final_download
    queued = Mock(return_value=True)
    dispatched = Mock(return_value=1)

    monkeypatch.setattr(service, "get_active_media_download_operation", Mock(return_value=None))
    monkeypatch.setattr(service, "queue_final_episode_redownload_if_ready", queued)
    monkeypatch.setattr(service, "dispatch_queued_media_download_operations", dispatched)

    result = asyncio.run(service.run_finalize_countdown_downloads(session, episode_id=episode.id))

    queued.assert_called_once_with(session, download.id)
    dispatched.assert_called_once_with(session)
    assert result.data["redownloads_queued"] == 1


def test_final_publication_cancels_countdown_attempt_and_waits_for_terminal(final_download, monkeypatch):
    from task_manager.tasks.workers.finalize_countdown_downloads import service

    session, episode, download = final_download
    countdown_operation = SimpleNamespace(
        id="countdown-operation",
        context={"episode_publish_status": "published_with_countdown"},
    )
    canceled = Mock()
    queued = Mock(return_value=False)

    monkeypatch.setattr(service, "get_active_media_download_operation", Mock(return_value=countdown_operation))
    monkeypatch.setattr(service, "cancel_media_download_operation", canceled)
    monkeypatch.setattr(service, "queue_final_episode_redownload_if_ready", queued)
    monkeypatch.setattr(service, "dispatch_queued_media_download_operations", Mock(return_value=0))

    result = asyncio.run(service.run_finalize_countdown_downloads(session, episode_id=episode.id))

    canceled.assert_called_once_with(
        "countdown-operation",
        reason="Final episode media became available",
        acknowledge=True,
    )
    queued.assert_called_once_with(session, download.id)
    assert download.redownload_when_final is True
    assert result.data["redownloads_queued"] == 0


def test_terminal_reconciliation_queues_pending_final_intent(final_download, monkeypatch):
    from task_manager.tasks import media_download_operations

    session, _episode, download = final_download
    created = Mock(return_value=SimpleNamespace(id="replacement"))

    monkeypatch.setattr(media_download_operations, "get_active_media_download_operation", Mock(return_value=None))
    monkeypatch.setattr(media_download_operations, "_has_active_media_download_run", Mock(return_value=False))
    monkeypatch.setattr(media_download_operations, "create_media_download_operation", created)

    assert media_download_operations.queue_final_episode_redownload_if_ready(session, download.id) is True
    session.flush()

    assert download.redownload_when_final is False
    created.assert_called_once()
    assert created.call_args.kwargs["source"] == "SYSTEM"
    assert created.call_args.kwargs["is_redownload"] is True
    assert created.call_args.kwargs["prepare_existing_artifact"] is True


def test_manual_countdown_request_persists_final_redownload_choice(final_download):
    from backend.api.endpoints.media_downloads.service import create_episode_download
    from backend.api.models.media_download import EpisodeDownloadAPICreate
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, episode, download = final_download
    episode.publish_status = "published_with_countdown"
    download.artifact_status = MediaDownloadArtifactStatus.ABSENT.value
    download.redownload_when_final = False
    session.commit()

    restarted = create_episode_download(
        session,
        episode.slug,
        EpisodeDownloadAPICreate(
            local_media_profile_id=download.local_media_profile_id,
            redownload_when_final=True,
        ),
    )
    session.flush()

    assert restarted.id == download.id
    assert restarted.redownload_when_final is True
