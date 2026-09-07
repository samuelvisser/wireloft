from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _make_show(session):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType
    show = Show(
        uuid="show-uuid", slug="test-show", title="Test Show", description=None,
        sharing_url="https://example.test/show", membership_level="FREE",
        type=ShowType.PODCAST.value, episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host", author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_episode(session, show, *, slug="episode", identifier="ep.2"):
    from backend.db.models import Episode, Season
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.helpers import generate_uuid
    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add(season)
    session.flush()
    episode = Episode(
        uuid=generate_uuid(), type="episode", show=show, season=season, index=2,
        episode_identifier=identifier, slug=slug, title="Unavailable episode", duration=100.0,
        publish_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
        sharing_url=f"https://example.test/{slug}",
        published_date=(datetime.now(timezone.utc) - timedelta(hours=6)).replace(tzinfo=None),
    )
    session.add(episode)
    show.set_meta("ep_id.latest_ep_num", "2")
    session.flush()
    return episode


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


def _mark_missing(session, episode, *, hours_ago: int):
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason, mark_episode_no_usable_media
    mark_episode_no_usable_media(
        session,
        episode,
        reason=NoUsableMediaReason.NOT_FOUND,
        now=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )
    session.commit()


def _patch_no_token(monkeypatch, service):
    monkeypatch.setattr(service, "DeviceAuthClient", lambda: Mock(get_token=lambda: None))


def test_mark_no_usable_media_refreshes_existing_metadata_rows(db_session):
    from backend.db.models.Metadata import Metadata
    from task_manager.tasks.helpers.episodes.unusable_media import (
        NO_USABLE_MEDIA_REASON_META_KEY,
        NO_USABLE_MEDIA_SINCE_META_KEY,
        NoUsableMediaReason,
        episode_no_usable_media_reason,
        episode_no_usable_media_since,
        mark_episode_no_usable_media,
    )

    show = _make_show(db_session)
    episode = _make_episode(db_session, show)
    first_seen = datetime.now(timezone.utc) - timedelta(hours=5)

    mark_episode_no_usable_media(
        db_session,
        episode,
        reason=NoUsableMediaReason.NOT_FOUND,
        now=first_seen,
    )
    db_session.commit()
    original_since = episode_no_usable_media_since(episode)

    mark_episode_no_usable_media(
        db_session,
        episode,
        reason=NoUsableMediaReason.NO_SHOW_TODAY,
        now=datetime.now(timezone.utc),
    )
    db_session.commit()

    rows = list(db_session.scalars(
        select(Metadata).where(
            Metadata.parent_table == "episodes",
            Metadata.parent_id == episode.id,
            Metadata.key.in_({NO_USABLE_MEDIA_REASON_META_KEY, NO_USABLE_MEDIA_SINCE_META_KEY}),
        )
    ))
    assert sum(row.key == NO_USABLE_MEDIA_REASON_META_KEY for row in rows) == 1
    assert sum(row.key == NO_USABLE_MEDIA_SINCE_META_KEY for row in rows) == 1
    assert episode_no_usable_media_reason(episode) is NoUsableMediaReason.NO_SHOW_TODAY
    assert episode_no_usable_media_since(episode) == original_since


def test_monitor_deletes_only_expired_episode_that_still_404s(db_session, monkeypatch):
    from backend.db.models import Episode
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service
    show = _make_show(db_session)
    episode = _make_episode(db_session, show)
    _mark_missing(db_session, episode, hours_ago=5)
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None): pass
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("not found", status_code=404)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_monitor_no_usable_media_episode(db_session, delete_after_minutes=240))
    assert db_session.get(Episode, episode_id) is None


def test_monitor_keeps_expired_episode_when_daily_wire_still_returns_it(db_session, monkeypatch):
    from backend.db.models import Episode
    from task_manager.tasks.helpers.episodes.unusable_media import episode_no_usable_media_reason, NoUsableMediaReason
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service
    show = _make_show(db_session)
    episode = _make_episode(db_session, show)
    _mark_missing(db_session, episode, hours_ago=5)
    episode_id = episode.id

    detail = SimpleNamespace(
        slug=episode.slug, title=episode.title, duration=5.0, video_url=None, audio_url=None,
        publish_status="PUBLISHED", is_downloadable=True,
    )
    class FakeClient:
        def __init__(self, access_token=None): pass
        def get_episode_details(self, slug, *, require_member_exclusive): return detail

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_monitor_no_usable_media_episode(db_session, delete_after_minutes=240))
    stored = db_session.get(Episode, episode_id)
    assert stored is not None
    assert episode_no_usable_media_reason(stored) is NoUsableMediaReason.MEDIA_UNUSABLE
    assert stored.early_delete_available is False


def test_force_delete_still_requires_fresh_404(db_session, monkeypatch):
    from backend.db.models import Episode
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service
    show = _make_show(db_session)
    episode = _make_episode(db_session, show)
    _mark_missing(db_session, episode, hours_ago=1)
    episode_id = episode.id

    detail = SimpleNamespace(
        slug=episode.slug, title=episode.title, duration=5.0, video_url=None, audio_url=None,
        publish_status="PUBLISHED", is_downloadable=True,
    )
    class FakeClient:
        def __init__(self, access_token=None): pass
        def get_episode_details(self, slug, *, require_member_exclusive): return detail

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_monitor_no_usable_media_episode(
        db_session, episode_id=episode_id, force=True, delete_after_minutes=240,
    ))
    assert db_session.get(Episode, episode_id) is not None


def test_force_delete_removes_target_immediately_when_it_still_404s(db_session, monkeypatch):
    from backend.db.models import Episode
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service
    show = _make_show(db_session)
    episode = _make_episode(db_session, show)
    _mark_missing(db_session, episode, hours_ago=1)
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None): pass
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("not found", status_code=404)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    asyncio.run(service.run_monitor_no_usable_media_episode(
        db_session, episode_id=episode_id, force=True, delete_after_minutes=240,
    ))
    assert db_session.get(Episode, episode_id) is None


def test_force_delete_requires_specific_episode(db_session):
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service
    with pytest.raises(ValueError, match="specific episode_id"):
        asyncio.run(service.run_monitor_no_usable_media_episode(db_session, force=True))
