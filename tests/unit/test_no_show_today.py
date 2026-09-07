from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


# ---------- detection ----------

def test_no_show_today_detection_uses_slug_only():
    from backend.utils.episode_slug import is_no_show_today_slug

    assert is_no_show_today_slug("matt-walsh-1809-no-show-today") is True
    assert is_no_show_today_slug("MATT-WALSH-1809-NO-SHOW-TODAY") is True
    assert is_no_show_today_slug("matt-walsh-1809") is False
    assert is_no_show_today_slug(None) is False


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


def _patch_no_token(monkeypatch, service):
    monkeypatch.setattr(
        service,
        "DeviceAuthClient",
        lambda: Mock(get_token=lambda: None),
    )


def _patch_usable_hls(monkeypatch):
    from task_manager.tasks.helpers.episodes import status

    monkeypatch.setattr(
        status,
        "get_vod_info",
        lambda _url: SimpleNamespace(seconds=100),
    )


# ---------- no-show state normalization ----------

def test_title_alone_does_not_make_episode_no_show_today(db_session):
    from task_manager.tasks.helpers.episodes.save import upsert_episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = upsert_episode(
        db_session,
        show=show,
        season=season,
        ep=_dw_episode_record("matt-walsh-1809", "The Matt Walsh Show - No Show Today"),
        index_value=1,
        ep_id="ep.1809",
    )

    assert episode.is_no_show_today is False


def test_slug_marks_no_show_today_without_persisted_boolean(db_session):
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.save import (
        resolve_dw_episodes,
        save_resolved_episodes_per_season_asc,
    )
    from task_manager.tasks.helpers.episodes.unusable_media import (
        NoUsableMediaReason,
        episode_no_usable_media_reason,
    )

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    record = _dw_episode_record("matt-walsh-1809-no-show-today", "Ordinary title")
    [resolved] = resolve_dw_episodes(
        episodes=[("ep.1809", record)],
        client=object(),
        require_member_exclusive=False,
    )

    assert resolved.status is EpisodePublishStatus.NO_USABLE_MEDIA
    assert resolved.unusable_media_reason is NoUsableMediaReason.NO_SHOW_TODAY

    _, saved = save_resolved_episodes_per_season_asc(
        db_session,
        show=show,
        season=season,
        episodes=[resolved],
        start_index=1,
    )
    episode = saved[0].episode
    assert episode.is_no_show_today is True
    assert episode.episode_identifier == "not-usable.1"
    assert episode.get_meta("no_usable_media.previous_identifier") == "ep.1809"
    assert episode_no_usable_media_reason(episode) is NoUsableMediaReason.NO_SHOW_TODAY
    assert "is_no_show_today" not in Episode.__table__.columns.keys()


def test_episode_api_does_not_return_is_no_show_today(db_session):
    from backend.api.models.episode import EpisodeAPIRead
    from task_manager.tasks.helpers.episodes.save import (
        resolve_dw_episodes,
        save_resolved_episodes_per_season_asc,
    )

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    [resolved] = resolve_dw_episodes(
        episodes=[("ep.1", _dw_episode_record("test-show-1-no-show-today", "Anything"))],
        client=object(),
        require_member_exclusive=False,
    )
    _, saved = save_resolved_episodes_per_season_asc(
        db_session,
        show=show,
        season=season,
        episodes=[resolved],
        start_index=1,
    )

    payload = EpisodeAPIRead.model_validate(saved[0].episode).model_dump(by_alias=True)
    assert "isNoShowToday" not in payload
    assert payload["earlyDeleteAvailable"] is False


# ---------- profile eligibility remains generic ----------

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


# ---------- no-usable-media monitoring ----------

def _mark_unusable_at(session, episode, reason, observed_at):
    from task_manager.tasks.helpers.episodes.unusable_media import mark_episode_no_usable_media

    mark_episode_no_usable_media(
        session,
        episode,
        reason=reason,
        now=observed_at,
    )


def test_monitor_keeps_recent_no_show_today(db_session, monkeypatch):
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
        slug="ep-no-show-today",
        ep_id="aux.1",
        title="No Show Today",
        index=1,
        published_at=(now - timedelta(hours=1)).replace(tzinfo=None),
    )
    _mark_unusable_at(
        db_session,
        episode,
        NoUsableMediaReason.NO_SHOW_TODAY,
        now - timedelta(hours=1),
    )
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return _dw_episode_detail(slug, "No Show Today")

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    assert db_session.get(Episode, episode_id) is not None


def test_monitor_keeps_old_no_show_today_while_dailywire_still_returns_it(db_session, monkeypatch):
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
        slug="ep-no-show-today",
        ep_id="aux.1",
        title="No Show Today",
        index=1,
        published_at=(now - timedelta(hours=5)).replace(tzinfo=None),
    )
    _mark_unusable_at(
        db_session,
        episode,
        NoUsableMediaReason.NO_SHOW_TODAY,
        now - timedelta(hours=5),
    )
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return _dw_episode_detail(slug, "No Show Today")

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    assert db_session.get(Episode, episode_id) is not None


def test_monitor_recovers_no_show_placeholder_that_became_real_episode(db_session, monkeypatch):
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
        slug="ep-no-show-today",
        ep_id="ep.1",
        title="No Show Today",
        index=1,
        published_at=(now - timedelta(hours=5)).replace(tzinfo=None),
    )
    _mark_unusable_at(
        db_session,
        episode,
        NoUsableMediaReason.NO_SHOW_TODAY,
        now - timedelta(hours=5),
    )
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return _dw_episode_detail("ep-real", "Episode 1: A Real Episode")

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    _patch_usable_hls(monkeypatch)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    stored = db_session.get(Episode, episode_id)
    assert stored is not None
    assert stored.slug == "ep-real"
    assert stored.is_no_show_today is False
    assert stored.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
    assert stored.episode_identifier == "ep.1"


def test_monitor_deletes_continuous_404_after_four_hours(db_session, monkeypatch):
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
    _mark_unusable_at(
        db_session,
        episode,
        NoUsableMediaReason.NOT_FOUND,
        now - timedelta(hours=5),
    )
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


def test_monitor_verifies_recent_404_but_does_not_delete_it(db_session, monkeypatch):
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
        slug="temporarily-missing",
        ep_id="ep.1",
        title="Real episode",
        index=1,
        published_at=(now - timedelta(hours=10)).replace(tzinfo=None),
    )
    _mark_unusable_at(
        db_session,
        episode,
        NoUsableMediaReason.NOT_FOUND,
        now - timedelta(hours=1),
    )
    db_session.commit()
    episode_id = episode.id
    calls = Mock()

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            calls(slug)
            raise MiddlewareAPIError("HTTP error 404: episode not found", status_code=404)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    calls.assert_called_once_with("temporarily-missing")
    assert db_session.get(Episode, episode_id) is not None


def test_monitor_recovers_episode_when_404_endpoint_has_usable_media(db_session, monkeypatch):
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
    _mark_unusable_at(
        db_session,
        episode,
        NoUsableMediaReason.NOT_FOUND,
        now - timedelta(hours=5),
    )
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return _dw_episode_detail(slug, "Real episode")

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    _patch_usable_hls(monkeypatch)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    stored = db_session.get(Episode, episode_id)
    assert stored is not None
    assert stored.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
    assert episode_no_usable_media_reason(stored) is None
    assert stored.episode_identifier == "ep.1"


def test_monitor_ignores_genuine_dw_processing(db_session, monkeypatch):
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


def test_monitor_noop_when_nothing_is_unusable(db_session, monkeypatch):
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    called = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", called)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_cleanup_episodes_stuck_without_media(db_session))

    called.assert_not_called()
