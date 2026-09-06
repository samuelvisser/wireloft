from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


# ---------- detection ----------

def test_is_no_show_today_title_matches_case_insensitively():
    from task_manager.tasks.helpers.episodes.no_show import is_no_show_today_title

    assert is_no_show_today_title("The Matt Walsh Show - No Show Today") is True
    assert is_no_show_today_title("no show today") is True
    assert is_no_show_today_title("NO SHOW TODAY") is True
    assert is_no_show_today_title("The Matt Walsh Show - Episode 1809") is False
    assert is_no_show_today_title("") is False
    assert is_no_show_today_title(None) is False


# ---------- shared fixtures ----------

def _make_show(session, *, slug="test-show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Test Show",
        description=None,
        sharing_url=f"https://example.test/{slug}",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_season(session, show, *, index=1, slug="season-1", name="One"):
    from backend.db.models import Season

    season = Season(show=show, index=index, slug=slug, name=name)
    session.add(season)
    session.flush()
    return season


def _make_episode(
        session,
        show,
        season,
        *,
        slug,
        ep_id,
        title,
        index,
        is_no_show_today=False,
        publish_status="published_final",
        published_at=None,
):
    from backend.db.models import Episode
    from backend.utils.helpers import generate_uuid

    published_at = published_at or datetime.now(timezone.utc).replace(tzinfo=None)
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=ep_id,
        slug=slug,
        title=title,
        duration=100.0,
        publish_status=publish_status,
        sharing_url=f"https://example.test/{slug}",
        published_date=published_at,
        is_no_show_today=is_no_show_today,
    )
    session.add(episode)
    session.flush()
    return episode


def _make_local_media_profile(session, *, slug="audio"):
    from backend.db.models import LocalMediaProfile

    profile = LocalMediaProfile(
        slug=slug,
        name=slug,
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format="format_audio_only",
    )
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _dw_episode_record(slug: str, title: str):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{slug}",
        slug=slug,
        title=title,
        description=None,
        duration=100,
        episode_number="1.00",
        display_episode_number="1",
        background_image_path=None,
        sharing_url=f"https://example.test/{slug}",
        publish_status="PUBLISHED",
        is_downloadable=True,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scheduled_date=None,
    )


def _dw_episode_detail(slug: str, title: str):
    from dailywire_api.records import DwEpisodeDetailRecord

    return DwEpisodeDetailRecord(
        **_dw_episode_record(slug, title).model_dump(mode="python", by_alias=False),
        audio_url="https://example.test/audio.mp3",
        video_url="https://example.test/video.m3u8",
        delivery_mode="VOD",
        progress=0,
        next_episode_url=None,
        playback_status=None,
    )


# ---------- no-show state normalization ----------

def test_upsert_episode_marks_no_show_today_as_no_usable_media(db_session):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.save import upsert_episode
    from task_manager.tasks.helpers.episodes.unusable_media import (
        NoUsableMediaReason,
        episode_no_usable_media_reason,
    )

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _dw_episode_record(
        "matt-walsh-ep-1809-no-show-today",
        "The Matt Walsh Show - No Show Today",
    )

    episode = upsert_episode(
        db_session,
        show=show,
        season=season,
        ep=ep,
        index_value=1,
        ep_id="ep.1809",
    )

    assert episode.is_no_show_today is True
    assert episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value
    assert episode.metadata_is_final is False
    assert episode_no_usable_media_reason(episode) is NoUsableMediaReason.NO_SHOW_TODAY


def test_upsert_episode_does_not_flag_a_real_episode(db_session):
    from task_manager.tasks.helpers.episodes.save import upsert_episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _dw_episode_record("matt-walsh-ep-1810", "Episode 1810: The Real Deal")

    episode = upsert_episode(
        db_session,
        show=show,
        season=season,
        ep=ep,
        index_value=1,
        ep_id="ep.1810",
    )

    assert episode.is_no_show_today is False


def test_upsert_episode_reflags_on_update(db_session):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.save import upsert_episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)

    ep = _dw_episode_record("matt-walsh-ep-1809", "Episode 1809")
    episode = upsert_episode(
        db_session,
        show=show,
        season=season,
        ep=ep,
        index_value=1,
        ep_id="ep.1809",
    )
    assert episode.is_no_show_today is False

    renamed = _dw_episode_record(
        "matt-walsh-ep-1809",
        "The Matt Walsh Show - No Show Today",
    )
    episode = upsert_episode(
        db_session,
        show=show,
        season=season,
        ep=renamed,
        index_value=1,
        ep_id="ep.1809",
    )
    assert episode.is_no_show_today is True
    assert episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value


# ---------- profile eligibility is generic ----------

def test_download_profile_excludes_unusable_and_processing_statuses(db_session):
    from backend.db.models.download_profile import PodcastDownloadProfile
    from backend.types.download_profile_types import EpIdType
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.workers.download_profile_worker._helpers import (
        get_download_profile_episodes,
    )

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)

    real_ep = _make_episode(
        db_session,
        show,
        season,
        slug="ep-real",
        ep_id="ep.1",
        title="Real episode",
        index=1,
    )
    unusable_ep = _make_episode(
        db_session,
        show,
        season,
        slug="ep-unusable",
        ep_id="aux.1",
        title="Unavailable episode",
        index=2,
        publish_status=EpisodePublishStatus.NO_USABLE_MEDIA.value,
    )
    processing_ep = _make_episode(
        db_session,
        show,
        season,
        slug="ep-processing",
        ep_id="aux.2",
        title="Processing episode",
        index=3,
        publish_status=EpisodePublishStatus.DW_PROCESSING.value,
    )

    profile = PodcastDownloadProfile(
        show=show,
        local_media_profile=lmp,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value, EpIdType.AUX.value],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        delete_older_episodes=False,
    )
    db_session.add(profile)
    db_session.commit()

    slugs = {episode.slug for episode in get_download_profile_episodes(db_session, profile)}
    assert real_ep.slug in slugs
    assert unusable_ep.slug not in slugs
    assert processing_ep.slug not in slugs


# ---------- stale NO_USABLE_MEDIA cleanup ----------

def _mark_unusable_at(episode, reason, observed_at):
    from task_manager.tasks.helpers.episodes.unusable_media import mark_episode_no_usable_media

    mark_episode_no_usable_media(episode, reason=reason, now=observed_at)


def _patch_no_token(monkeypatch, service):
    monkeypatch.setattr(
        service,
        "DeviceAuthClient",
        lambda: Mock(get_token=lambda: None),
    )


def test_cleanup_keeps_recent_no_show_today(db_session, monkeypatch):
    from backend.db.models import Episode
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    now = datetime.now(timezone.utc)
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        slug="ep-no-show",
        ep_id="aux.1",
        title="No Show Today",
        index=1,
        is_no_show_today=True,
        published_at=(now - timedelta(hours=1)).replace(tzinfo=None),
    )
    _mark_unusable_at(episode, NoUsableMediaReason.NO_SHOW_TODAY, now - timedelta(hours=1))
    db_session.commit()
    episode_id = episode.id

    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    assert db_session.get(Episode, episode_id) is not None


def test_cleanup_deletes_no_show_after_four_hour_grace(db_session, monkeypatch):
    from backend.db.models import Episode
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    now = datetime.now(timezone.utc)
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        slug="ep-no-show",
        ep_id="aux.1",
        title="No Show Today",
        index=1,
        is_no_show_today=True,
        published_at=(now - timedelta(hours=5)).replace(tzinfo=None),
    )
    _mark_unusable_at(episode, NoUsableMediaReason.NO_SHOW_TODAY, now - timedelta(hours=5))
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return _dw_episode_detail(slug, "The Test Show - No Show Today")

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    assert db_session.get(Episode, episode_id) is None


def test_cleanup_preserves_no_show_that_became_real_episode(db_session, monkeypatch):
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    now = datetime.now(timezone.utc)
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        slug="ep-no-show",
        ep_id="aux.1",
        title="No Show Today",
        index=1,
        is_no_show_today=True,
        published_at=(now - timedelta(hours=5)).replace(tzinfo=None),
    )
    _mark_unusable_at(episode, NoUsableMediaReason.NO_SHOW_TODAY, now - timedelta(hours=5))
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return _dw_episode_detail(slug, "Episode 1: A Real Episode")

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    stored = db_session.get(Episode, episode_id)
    assert stored is not None
    assert stored.is_no_show_today is False
    assert stored.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value


def test_cleanup_deletes_continuous_404_after_four_hours(db_session, monkeypatch):
    from backend.db.models import Episode
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    now = datetime.now(timezone.utc)
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        slug="bad-remote-episode",
        ep_id="ep.1",
        title="Real episode",
        index=1,
        published_at=(now - timedelta(hours=5)).replace(tzinfo=None),
    )
    _mark_unusable_at(episode, NoUsableMediaReason.NOT_FOUND, now - timedelta(hours=5))
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("HTTP error 404: episode not found", status_code=404)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)

    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    assert db_session.get(Episode, episode_id) is None


def test_cleanup_does_not_verify_404_until_incident_is_four_hours_old(db_session, monkeypatch):
    from backend.db.models import Episode
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    now = datetime.now(timezone.utc)
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        slug="temporarily-missing",
        ep_id="ep.1",
        title="Real episode",
        index=1,
        published_at=(now - timedelta(hours=10)).replace(tzinfo=None),
    )
    _mark_unusable_at(episode, NoUsableMediaReason.NOT_FOUND, now - timedelta(hours=1))
    db_session.commit()
    episode_id = episode.id

    client = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", lambda access_token=None: client)
    _patch_no_token(monkeypatch, service)

    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    client.get_episode_details.assert_not_called()
    assert db_session.get(Episode, episode_id) is not None


def test_cleanup_keeps_episode_when_404_endpoint_recovers(db_session, monkeypatch):
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.unusable_media import (
        NoUsableMediaReason,
        episode_no_usable_media_reason,
    )
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    now = datetime.now(timezone.utc)
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        slug="recovered-episode",
        ep_id="ep.1",
        title="Real episode",
        index=1,
        published_at=(now - timedelta(hours=5)).replace(tzinfo=None),
    )
    _mark_unusable_at(episode, NoUsableMediaReason.NOT_FOUND, now - timedelta(hours=5))
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return _dw_episode_detail(slug, "Real episode")

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)

    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    stored = db_session.get(Episode, episode_id)
    assert stored is not None
    assert stored.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
    assert episode_no_usable_media_reason(stored) is None


def test_cleanup_ignores_genuine_dw_processing(db_session, monkeypatch):
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        slug="real-processing",
        ep_id="ep.1",
        title="Real processing episode",
        index=1,
        publish_status=EpisodePublishStatus.DW_PROCESSING.value,
        published_at=(datetime.now(timezone.utc) - timedelta(hours=10)).replace(tzinfo=None),
    )
    db_session.commit()
    episode_id = episode.id

    called = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", called)
    _patch_no_token(monkeypatch, service)

    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    assert db_session.get(Episode, episode_id) is not None
    called.assert_not_called()


def test_cleanup_noop_when_nothing_is_unusable(db_session, monkeypatch):
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    called = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", called)
    _patch_no_token(monkeypatch, service)

    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    called.assert_not_called()
