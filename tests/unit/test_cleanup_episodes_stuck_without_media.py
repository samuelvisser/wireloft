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


def _make_replacement_episode(session, original, *, slug="canonical-slug"):
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.helpers import generate_uuid
    from task_manager.tasks.helpers.episodes.quarantine import PREVIOUS_IDENTIFIER_META_KEY

    previous_identifier = original.get_meta(PREVIOUS_IDENTIFIER_META_KEY)
    assert previous_identifier
    replacement = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=original.show,
        season=original.season,
        index=original.index + 1,
        episode_identifier=previous_identifier,
        slug=slug,
        title=original.title,
        duration=100.0,
        publish_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
        sharing_url=f"https://example.test/{slug}",
        published_date=original.published_date,
    )
    session.add(replacement)
    session.flush()
    return replacement


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


def test_target_result_contains_facts_not_ui_copy():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service

    for outcome in ("recovered", "replaced", "deleted", "retained", "unverified", "already_resolved"):
        result = service._target_result(
            episode_id=42,
            outcome=outcome,
            recovered_status=EpisodePublishStatus.PUBLISHED_FINAL,
            episode_slug="canonical-slug",
            verified=1,
            recovered=1,
            removed=0,
        )
        assert result.summary == "No-usable-media episode verification completed"
        assert result.data == {
            "episode_id": 42,
            "outcome": outcome,
            "verified": 1,
            "recovered": 1,
            "removed": 0,
            "publish_status": EpisodePublishStatus.PUBLISHED_FINAL.value,
            "episode_slug": "canonical-slug",
        }


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
    result = asyncio.run(service.run_monitor_no_usable_media_episode(
        db_session, episode_id=episode_id, force=True, delete_after_minutes=240,
    ))
    assert db_session.get(Episode, episode_id) is not None
    assert result.data["outcome"] == "retained"
    assert result.data["removed"] == 0


def test_force_delete_reports_recovery_and_new_status(db_session, monkeypatch):
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service

    show = _make_show(db_session)
    episode = _make_episode(db_session, show)
    _mark_missing(db_session, episode, hours_ago=1)
    episode_id = episode.id
    detail = SimpleNamespace(slug=episode.slug)

    class FakeClient:
        def __init__(self, access_token=None): pass
        def get_episode_details(self, slug, *, require_member_exclusive): return detail

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    monkeypatch.setattr(
        service,
        "observe_episode_detail",
        lambda _detail, *, inspect_static_media: SimpleNamespace(
            status=EpisodePublishStatus.PUBLISHED_FINAL,
            has_usable_media=True,
        ),
    )
    monkeypatch.setattr(
        service,
        "resolve_episode_status",
        lambda _detail, *, snapshot: SimpleNamespace(status=EpisodePublishStatus.PUBLISHED_FINAL),
    )
    monkeypatch.setattr(service, "update_episode_from_dailywire", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "reconcile_episode_identifier", lambda *_args, **_kwargs: None)

    result = asyncio.run(service.run_monitor_no_usable_media_episode(
        db_session, episode_id=episode_id, force=True, delete_after_minutes=240,
    ))

    stored = db_session.get(Episode, episode_id)
    assert stored is not None
    assert stored.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
    assert result.data["outcome"] == "recovered"
    assert result.data["publish_status"] == EpisodePublishStatus.PUBLISHED_FINAL.value
    assert result.data["episode_slug"] == episode.slug
    assert result.data["recovered"] == 1
    assert result.data["removed"] == 0


def test_force_delete_reports_replacement_as_recovered_state(db_session, monkeypatch):
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service

    show = _make_show(db_session)
    episode = _make_episode(db_session, show, slug="wrong-slug")
    _mark_missing(db_session, episode, hours_ago=1)
    episode_id = episode.id
    replacement = _make_replacement_episode(db_session, episode, slug="canonical-slug")
    replacement_id = replacement.id
    db_session.commit()

    class FakeClient:
        def __init__(self, access_token=None): pass
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("not found", status_code=404)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    _patch_no_token(monkeypatch, service)
    result = asyncio.run(service.run_monitor_no_usable_media_episode(
        db_session, episode_id=episode_id, force=True, delete_after_minutes=240,
    ))

    assert db_session.get(Episode, episode_id) is None
    stored_replacement = db_session.get(Episode, replacement_id)
    assert stored_replacement is not None
    assert stored_replacement.slug == "canonical-slug"
    assert result.data["outcome"] == "replaced"
    assert result.data["publish_status"] == EpisodePublishStatus.PUBLISHED_FINAL.value
    assert result.data["episode_slug"] == "canonical-slug"
    assert result.data["removed"] == 1


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
    result = asyncio.run(service.run_monitor_no_usable_media_episode(
        db_session, episode_id=episode_id, force=True, delete_after_minutes=240,
    ))
    assert db_session.get(Episode, episode_id) is None
    assert result.data["outcome"] == "deleted"
    assert result.data["removed"] == 1
    assert result.data["recovered"] == 0


def test_force_delete_requires_specific_episode(db_session):
    from task_manager.tasks.workers.monitor_no_usable_media_episode import service
    with pytest.raises(ValueError, match="specific episode_id"):
        asyncio.run(service.run_monitor_no_usable_media_episode(db_session, force=True))
