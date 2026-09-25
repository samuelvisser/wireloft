from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def final_download(tmp_path):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)

    show = Show(
        uuid="show-uuid",
        slug="show",
        title="Show",
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
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="episode",
        title="Episode",
        duration=100.0,
        publish_status="published_final",
        sharing_url="https://example.test/episode",
    )
    profile = LocalMediaProfile(
        slug="audio",
        name="Audio",
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

    session, episode, _download = final_download
    queued = Mock(return_value=True)
    dispatched = Mock(return_value=1)

    monkeypatch.setattr(service, "get_active_media_download_operation", Mock(return_value=None))
    monkeypatch.setattr(service, "queue_final_episode_redownload_if_ready", queued)
    monkeypatch.setattr(service, "dispatch_queued_media_download_operations", dispatched)

    result = asyncio.run(service.run_finalize_countdown_downloads(session, episode_id=episode.id))

    queued.assert_called_once()
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
    monkeypatch.setattr(service, "cancel_operation", canceled)
    monkeypatch.setattr(service, "queue_final_episode_redownload_if_ready", queued)
    monkeypatch.setattr(service, "dispatch_queued_media_download_operations", Mock(return_value=0))

    result = asyncio.run(service.run_finalize_countdown_downloads(session, episode_id=episode.id))
    session.refresh(download)

    canceled.assert_called_once_with(
        "countdown-operation",
        reason="Final episode media became available",
        acknowledge=True,
    )
    queued.assert_called_once_with(session, download.id)
    assert download.redownload_when_final is True
    assert result.data["redownloads_queued"] == 0


def test_final_publication_keeps_already_final_attempt(final_download, monkeypatch):
    from task_manager.tasks.workers.finalize_countdown_downloads import service

    session, episode, download = final_download
    final_operation = SimpleNamespace(
        id="final-operation",
        context={"episode_publish_status": "published_final"},
    )
    canceled = Mock()

    def consume_intent(_session, _download_id):
        download.redownload_when_final = False
        return False

    queued = Mock(side_effect=consume_intent)
    monkeypatch.setattr(service, "get_active_media_download_operation", Mock(return_value=final_operation))
    monkeypatch.setattr(service, "cancel_operation", canceled)
    monkeypatch.setattr(service, "queue_final_episode_redownload_if_ready", queued)
    monkeypatch.setattr(service, "dispatch_queued_media_download_operations", Mock(return_value=0))

    asyncio.run(service.run_finalize_countdown_downloads(session, episode_id=episode.id))
    session.refresh(download)

    assert download.redownload_when_final is False
    canceled.assert_not_called()
    queued.assert_called_once_with(session, download.id)



def test_download_records_publish_status_from_attempt_start(final_download, monkeypatch, tmp_path):
    from dailywire_downloader import DownloadResult
    from task_manager.tasks.helpers.downloads.engine import DownloadExecution, ResolvedDownloadSource
    from task_manager.tasks.workers.download_episode import service

    session, episode, download = final_download
    episode.publish_status = "published_with_countdown"
    session.commit()

    destination = tmp_path / "captured-countdown.m4a"

    def fake_download(*args, **kwargs):
        # Simulate the exact race this feature must preserve correctly: the
        # episode becomes final while bytes from the countdown attempt are still
        # being transferred.
        episode.publish_status = "published_final"
        session.commit()
        destination.write_bytes(b"downloaded countdown bytes")
        return DownloadExecution(
            result=DownloadResult(
                path=str(destination),
                bytes_downloaded=26,
            ),
            source=ResolvedDownloadSource(
                url="https://example.test/audio.m4a",
                format_downloaded="audio",
                use_hls=False,
                remux_to_mp4=False,
                extension="m4a",
                audio_only=True,
            ),
        )

    monkeypatch.setattr(service, "_download_with_url_refresh", fake_download)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id))
    session.refresh(download)
    session.refresh(episode)

    assert episode.publish_status == "published_final"
    assert download.downloaded_publish_status == "published_with_countdown"



def test_terminal_reconciliation_consumes_pending_final_intent(final_download, monkeypatch):
    from task_manager.tasks import media_download_operations

    session, _episode, download = final_download
    prepared = Mock()
    created = Mock(return_value=SimpleNamespace(id="replacement"))

    monkeypatch.setattr(media_download_operations, "get_active_media_download_operation", Mock(return_value=None))
    monkeypatch.setattr(media_download_operations, "_has_active_media_download_run", Mock(return_value=False))
    monkeypatch.setattr(media_download_operations, "prepare_media_download_artifact", prepared)
    monkeypatch.setattr(media_download_operations, "create_media_download_operation", created)

    assert media_download_operations.queue_final_episode_redownload_if_ready(session, download.id) is True
    session.flush()

    assert download.redownload_when_final is False
    prepared.assert_called_once_with(session, download)
    created.assert_called_once()
    assert created.call_args.kwargs["source"] == "SYSTEM"
    assert created.call_args.kwargs["is_redownload"] is True
