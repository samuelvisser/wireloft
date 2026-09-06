from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


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


def _make_episode(session, show, *, slug="episode"):
    from backend.db.models import Episode, Season
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.helpers import generate_uuid

    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add(season)
    session.flush()

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug=slug,
        title="Processing episode",
        duration=100.0,
        publish_status=EpisodePublishStatus.DW_PROCESSING.value,
        sharing_url=f"https://example.test/{slug}",
        published_date=(datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None),
        is_no_show_today=False,
    )
    session.add(episode)
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


def _patch_no_token(monkeypatch, service):
    monkeypatch.setattr(
        service,
        "DeviceAuthClient",
        lambda: Mock(get_token=lambda: None),
    )


def test_cleanup_uses_configured_processing_delete_delay(db_session, monkeypatch):
    from backend.db.models import Episode
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.helpers.episodes.processing import (
        DwProcessingReason,
        mark_episode_dw_processing,
    )
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    show = _make_show(db_session)
    episode = _make_episode(db_session, show)
    mark_episode_dw_processing(
        episode,
        reason=DwProcessingReason.NOT_FOUND,
        now=datetime.now(timezone.utc) - timedelta(hours=2),
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

    asyncio.run(
        service.run_cleanup_episodes_stuck_without_media(
            db_session,
            delete_after_minutes=60,
        )
    )

    assert db_session.get(Episode, episode_id) is None


def test_force_cleanup_deletes_targeted_processing_episode_immediately(db_session, monkeypatch):
    from backend.db.models import Episode
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    show = _make_show(db_session)
    episode = _make_episode(db_session, show, slug="early-delete")
    db_session.commit()
    episode_id = episode.id

    class UnexpectedAuthClient:
        def __init__(self):
            raise AssertionError("force cleanup should not contact Daily Wire authentication")

    monkeypatch.setattr(service, "DeviceAuthClient", UnexpectedAuthClient)

    asyncio.run(
        service.run_cleanup_episodes_stuck_without_media(
            db_session,
            episode_id=episode_id,
            force=True,
            delete_after_minutes=4 * 60,
        )
    )

    assert db_session.get(Episode, episode_id) is None


def test_force_cleanup_requires_specific_episode(db_session):
    from task_manager.tasks.workers.cleanup_episodes_stuck_without_media import service

    with pytest.raises(ValueError, match="specific episode_id"):
        asyncio.run(
            service.run_cleanup_episodes_stuck_without_media(
                db_session,
                force=True,
            )
        )
