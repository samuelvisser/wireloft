from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _make_show(session):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid="episode-limit-show-uuid",
        slug="episode-limit-show",
        title="Episode Limit Show",
        description=None,
        sharing_url="https://example.test/episode-limit-show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_season(session, show):
    from backend.db.models import Season

    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add(season)
    session.flush()
    return season


def _make_episode(session, show, season, *, index: int, published_at: datetime):
    from backend.db.models import Episode
    from backend.utils.helpers import generate_uuid

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=f"ep.{index}",
        slug=f"episode-{index}",
        title=f"Episode {index}",
        duration=100.0,
        publish_status="published_final",
        sharing_url=f"https://example.test/episode-{index}",
        published_date=published_at,
    )
    session.add(episode)
    session.flush()
    return episode


def _make_local_media_profile(session):
    from backend.db.models import LocalMediaProfile

    profile = LocalMediaProfile(
        slug="episode-limit-audio",
        name="Episode limit audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    session.add(profile)
    session.flush()
    return profile


def _make_podcast_profile(session, show, local_media_profile, *, count: int, delete_older: bool = False):
    from backend.db.models.download_profile import PodcastDownloadProfile
    from backend.types.download_profile_types import EpIdType

    profile = PodcastDownloadProfile(
        show=show,
        local_media_profile=local_media_profile,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=count,
        delete_older_episodes=delete_older,
    )
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from config import get_settings

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    yield session
    session.close()
    engine.dispose()


def test_podcast_profile_selects_only_latest_episode_count(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    local_media_profile = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episodes = [
        _make_episode(db_session, show, season, index=index, published_at=now - timedelta(days=4 - index))
        for index in range(1, 5)
    ]
    profile = _make_podcast_profile(db_session, show, local_media_profile, count=2)

    selected = get_download_profile_episodes(db_session, profile)
    assert [episode.id for episode in selected] == [episodes[3].id, episodes[2].id]


def test_episode_scoped_run_still_checks_global_latest_set(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    local_media_profile = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old_episode = _make_episode(db_session, show, season, index=1, published_at=now - timedelta(days=10))
    newest_episode = _make_episode(db_session, show, season, index=2, published_at=now)
    profile = _make_podcast_profile(db_session, show, local_media_profile, count=1)

    assert get_download_profile_episodes(db_session, profile, only_episode=old_episode) == []
    assert get_download_profile_episodes(db_session, profile, only_episode=newest_episode) == [newest_episode]


def test_episode_count_cleanup_removes_available_and_absent_artifacts_outside_limit(db_session, tmp_path):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from task_manager.tasks.workers.download_profile_worker._helpers import cleanup_older_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    local_media_profile = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episodes = [
        _make_episode(db_session, show, season, index=index, published_at=now - timedelta(days=4 - index))
        for index in range(1, 5)
    ]
    profile = _make_podcast_profile(db_session, show, local_media_profile, count=2, delete_older=True)

    completed_file = tmp_path / "old-completed.m4a"
    completed_file.write_bytes(b"data")
    completed = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episodes[0].id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(completed_file),
    )
    absent = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episodes[1].id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        file_path=str(tmp_path / "old-absent.m4a"),
    )
    kept = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episodes[2].id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(tmp_path / "kept.m4a"),
    )
    db_session.add_all([completed, absent, kept])
    db_session.commit()

    removed = cleanup_older_episodes(db_session, profile)
    db_session.commit()

    assert removed == 2
    assert not completed_file.exists()
    remaining_episode_ids = {row.media_item_id for row in db_session.query(EpisodeMediaDownload).all()}
    assert remaining_episode_ids == {episodes[2].id}


def test_episode_count_cleanup_keeps_available_files_when_delete_older_is_off(db_session, tmp_path):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from task_manager.tasks.workers.download_profile_worker._helpers import cleanup_older_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    local_media_profile = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    completed_episode = _make_episode(db_session, show, season, index=1, published_at=now - timedelta(days=2))
    absent_episode = _make_episode(db_session, show, season, index=2, published_at=now - timedelta(days=1))
    _make_episode(db_session, show, season, index=3, published_at=now)
    profile = _make_podcast_profile(db_session, show, local_media_profile, count=1, delete_older=False)

    completed_file = tmp_path / "retained-old.m4a"
    completed_file.write_bytes(b"data")
    completed = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=completed_episode.id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(completed_file),
    )
    absent = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=absent_episode.id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        file_path=str(tmp_path / "stale-absent.m4a"),
    )
    db_session.add_all([completed, absent])
    db_session.commit()

    removed = cleanup_older_episodes(db_session, profile)
    db_session.commit()

    assert removed == 1
    assert completed_file.exists()
    rows = db_session.query(EpisodeMediaDownload).all()
    assert len(rows) == 1
    assert rows[0].media_item_id == completed_episode.id
    assert rows[0].artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
