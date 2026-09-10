from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _make_show(session):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid="starting-from-show-uuid",
        slug="starting-from-show",
        title="Starting From Show",
        description=None,
        sharing_url="https://example.test/starting-from-show",
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
        slug="starting-from-audio",
        name="Starting from audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    session.add(profile)
    session.flush()
    return profile


def _make_podcast_profile(session, show, local_media_profile, *, starting_from: date):
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
        download_episode_count=0,
        download_starting_from=starting_from,
        delete_older_episodes=True,
    )
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from config import get_settings
    from task_manager.tasks.workers.download_profile_worker import _helpers

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    monkeypatch.setattr(_helpers, "get_settings", lambda: SimpleNamespace(timezone="UTC"))
    yield session
    session.close()
    engine.dispose()


def test_podcast_profile_downloads_from_fixed_date_inclusively(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    local_media_profile = _make_local_media_profile(db_session)
    before = _make_episode(
        db_session,
        show,
        season,
        index=1,
        published_at=datetime(2026, 1, 9, 12, tzinfo=timezone.utc),
    )
    on_date = _make_episode(
        db_session,
        show,
        season,
        index=2,
        published_at=datetime(2026, 1, 10, 0, tzinfo=timezone.utc),
    )
    later = _make_episode(
        db_session,
        show,
        season,
        index=3,
        published_at=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
    )
    profile = _make_podcast_profile(
        db_session,
        show,
        local_media_profile,
        starting_from=date(2026, 1, 10),
    )

    selected = get_download_profile_episodes(db_session, profile)
    assert {episode.id for episode in selected} == {on_date.id, later.id}
    assert before.id not in {episode.id for episode in selected}

    assert get_download_profile_episodes(db_session, profile, only_episode=before) == []
    assert get_download_profile_episodes(db_session, profile, only_episode=later) == [later]


def test_starting_from_never_deletes_older_downloads(db_session, tmp_path):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from task_manager.tasks.workers.download_profile_worker._helpers import cleanup_older_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    local_media_profile = _make_local_media_profile(db_session)
    old_episode = _make_episode(
        db_session,
        show,
        season,
        index=1,
        published_at=datetime(2025, 1, 1, 12, tzinfo=timezone.utc),
    )
    profile = _make_podcast_profile(
        db_session,
        show,
        local_media_profile,
        starting_from=date(2026, 1, 1),
    )

    existing_file = tmp_path / "existing-old-download.m4a"
    existing_file.write_bytes(b"data")
    existing = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=old_episode.id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        file_path=str(existing_file),
    )
    db_session.add(existing)
    db_session.commit()

    assert cleanup_older_episodes(db_session, profile) == 0
    assert existing_file.exists()
    assert db_session.get(EpisodeMediaDownload, existing.id) is existing


def test_api_rejects_starting_from_with_rolling_limit():
    from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPICreate

    with pytest.raises(ValidationError, match="Download starting from can only be used"):
        PodcastDownloadProfileAPICreate(
            show_id=1,
            local_media_profile_id=1,
            enable_profile=True,
            ep_id_type_list=["ep"],
            download_with_countdown=False,
            redownload_final=False,
            download_days_in_past=30,
            download_episode_count=0,
            download_starting_from=date(2026, 1, 1),
            delete_older_episodes=True,
        )
