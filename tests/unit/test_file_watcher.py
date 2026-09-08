from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _db_with_download(tmp_path, *, file_name="episode.m4a", write_bytes: bytes | None = b"hello world"):
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

    file_path = tmp_path / file_name
    if write_bytes is not None:
        file_path.write_bytes(write_bytes)

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(file_path),
        downloaded_bytes=len(write_bytes) if write_bytes is not None else None,
    )
    session.add(download)
    session.commit()

    return session, engine, show, episode, download


@pytest.fixture(autouse=True)
def _enable_file_watcher(monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings().file_watcher, "enabled", True)
    monkeypatch.setattr(get_settings().file_watcher, "verify_file_size", True)
    yield


def _run(session, **kwargs):
    from task_manager.tasks.workers.file_watcher.service import run_file_watcher

    asyncio.run(run_file_watcher(session, **kwargs))


def test_healthy_download_is_left_untouched(tmp_path):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path)

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
    assert download.artifact_error is None

    session.close()
    engine.dispose()


def test_deleted_file_is_flagged_missing(tmp_path):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path)
    import os
    os.remove(download.file_path)

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.MISSING.value
    assert "not found" in download.artifact_error

    session.close()
    engine.dispose()


def test_renamed_away_file_is_flagged_missing(tmp_path):
    """A file moved/renamed outside WireLoft is indistinguishable from a deletion."""
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path)
    import os
    os.rename(download.file_path, tmp_path / "renamed-by-user.m4a")

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.MISSING.value

    session.close()
    engine.dispose()


def test_empty_file_is_flagged_corrupted(tmp_path):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path, write_bytes=b"")

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.CORRUPTED.value
    assert "empty" in download.artifact_error

    session.close()
    engine.dispose()


def test_truncated_file_is_flagged_corrupted(tmp_path):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path, write_bytes=b"0123456789")
    with open(download.file_path, "wb") as file:
        file.write(b"012")

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.CORRUPTED.value
    assert "well under" in download.artifact_error

    session.close()
    engine.dispose()


def test_modest_shrinkage_is_tolerated(tmp_path):
    """A remuxed .mp4 may be smaller than the bytes fetched for its raw stream."""
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path, write_bytes=b"x" * 1000)
    with open(download.file_path, "wb") as file:
        file.write(b"x" * 900)

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value

    session.close()
    engine.dispose()


def test_truncation_check_can_be_disabled(tmp_path, monkeypatch):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from config import get_settings

    monkeypatch.setattr(get_settings().file_watcher, "verify_file_size", False)

    session, engine, _show, _episode, download = _db_with_download(tmp_path, write_bytes=b"0123456789")
    with open(download.file_path, "wb") as file:
        file.write(b"012")

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value

    session.close()
    engine.dispose()


def test_missing_download_recovers_once_file_reappears(tmp_path):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path)
    download.artifact_status = MediaDownloadArtifactStatus.MISSING.value
    download.artifact_error = "File not found"
    session.commit()

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
    assert download.artifact_error is None

    session.close()
    engine.dispose()


def test_absent_artifacts_are_never_touched(tmp_path):
    """An active attempt is TaskRun state; an absent artifact is not watched as a file."""
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session, engine, _show, _episode, download = _db_with_download(tmp_path, write_bytes=None)
    download.artifact_status = MediaDownloadArtifactStatus.ABSENT.value
    download.file_path = str(tmp_path / "not-written-yet.m4a")
    session.commit()

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
    assert download.artifact_error is None

    session.close()
    engine.dispose()


def test_disabled_file_watcher_skips_everything(tmp_path, monkeypatch):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from config import get_settings

    monkeypatch.setattr(get_settings().file_watcher, "enabled", False)

    session, engine, _show, _episode, download = _db_with_download(tmp_path)
    import os
    os.remove(download.file_path)

    _run(session)

    assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value

    session.close()
    engine.dispose()


def test_scan_can_be_scoped_to_one_show(tmp_path):
    from backend.db.models import Episode, LocalMediaProfile, Season, Show
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid
    import os

    session, engine, show, _episode, download = _db_with_download(tmp_path)

    other_show = Show(
        uuid="show-uuid-2",
        slug="other-show",
        title="Other Show",
        description=None,
        sharing_url="https://example.test/other-show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    other_season = Season(show=other_show, index=1, slug="other-season-2026", name="2026")
    other_episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=other_show,
        season=other_season,
        index=1,
        episode_identifier="ep.101",
        slug="other-episode-101",
        title="Other Ep. 101",
        description=None,
        duration=100.0,
        publish_status="published_final",
        sharing_url="https://example.test/other-ep",
    )
    profile = session.get(LocalMediaProfile, download.local_media_profile_id)
    other_file = tmp_path / "other-episode.m4a"
    other_file.write_bytes(b"content")
    other_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=None,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(other_file),
        downloaded_bytes=7,
    )
    session.add_all([other_show, other_season, other_episode])
    session.commit()
    other_download.media_item_id = other_episode.id
    session.add(other_download)
    session.commit()

    os.remove(download.file_path)
    os.remove(other_file)

    _run(session, show_id=show.id)

    assert download.artifact_status == MediaDownloadArtifactStatus.MISSING.value
    assert other_download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value

    session.close()
    engine.dispose()
