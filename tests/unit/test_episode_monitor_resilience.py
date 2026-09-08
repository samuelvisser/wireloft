from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeScheduler:
    def __init__(self) -> None:
        self.job: dict | None = None
    def add_job(self, function, **kwargs):
        self.job = {"function": function, **kwargs}
        return SimpleNamespace(id=kwargs["id"])


def test_recurring_pending_monitor_disables_task_retries(monkeypatch):
    from task_manager.tasks.workers.monitor_pending_episode import scheduling
    scheduler = FakeScheduler()
    monkeypatch.setattr(scheduling, "start_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        scheduling, "get_settings",
        lambda: SimpleNamespace(
            new_episode_schedule=SimpleNamespace(monitor_pending_episode_cron="*/1 * * * *"),
            timezone="Europe/Amsterdam",
        ),
    )
    scheduling.schedule_episode_monitor(resource_id=501)
    assert scheduler.job is not None
    assert scheduler.job["kwargs"]["def_key"] == "monitor_pending_episode"
    assert scheduler.job["kwargs"]["max_retries"] == 0
    assert scheduler.job["max_instances"] == 1
    assert scheduler.job["coalesce"] is True


def _episode_record(slug: str):
    from dailywire_api.records import DwEpisodeRecord
    return DwEpisodeRecord(
        dw_id=f"remote-{slug}", slug=slug, title="Live episode", description=None,
        duration=3600, episode_number="101.00", display_episode_number="101.00",
        background_image_path=None, sharing_url=f"https://example.test/{slug}",
        publish_status="LIVE", is_downloadable=False, available_for=[],
        thumbnail_landscape_path=None, thumbnail_portrait_path=None, thumbnail_square_path=None,
        published_date=datetime(2026, 9, 5, 12, tzinfo=timezone.utc), scheduled_date=None,
    )


def _monitor_fixture():
    from backend.db import Base
    from backend.db.models import Season, Show
    from backend.types.episode_types import EpisodePublishStatus
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from task_manager.tasks.helpers.episodes.save import upsert_episode
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show = Show(
        uuid="show-uuid", slug="test-show", title="Test Show", description=None,
        sharing_url="https://example.test/show", membership_level="FREE",
        type=ShowType.PODCAST.value, episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Test Host", author_slug="test-host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add_all([show, season])
    session.flush()
    episode = upsert_episode(
        session, show=show, season=season,
        ep=_episode_record("live-episode").model_copy(update={"publish_status": EpisodePublishStatus.LIVE.value}, deep=True),
        index_value=2, ep_id="ep.101",
    )
    show.set_meta("ep_id.latest_ep_num", "101")
    session.commit()
    return engine, session, show, episode


def test_pending_monitor_marks_unreconciled_404_as_no_usable_media(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason, episode_no_usable_media_reason, episode_no_usable_media_since
    from task_manager.tasks.workers.monitor_pending_episode import service
    engine, session, show, episode = _monitor_fixture()

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("not found", status_code=404)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    monkeypatch.setattr(service, "_try_reconcile_slug_after_404", lambda *args, **kwargs: False)
    result = asyncio.run(service.run_monitor_pending_episode(
        session, episode_id=episode.id, episode_slug=episode.slug, show_slug=show.slug,
        episode_identifier=episode.episode_identifier, episode_index=episode.index,
    ))
    assert result is EpisodePublishStatus.NO_USABLE_MEDIA
    session.expire_all()
    stored = session.get(type(episode), episode.id)
    assert stored.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value
    assert stored.episode_identifier == "not-usable.1"
    assert stored.get_meta("no_usable_media.previous_identifier") == "ep.101"
    assert episode_no_usable_media_reason(stored) is NoUsableMediaReason.NOT_FOUND
    assert episode_no_usable_media_since(stored) is not None
    session.close()
    engine.dispose()


def test_pending_monitor_still_raises_non_404_dailywire_errors(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.workers.monitor_pending_episode import service
    engine, session, show, episode = _monitor_fixture()

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("HTTP error 503", status_code=503)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    with pytest.raises(MiddlewareAPIError, match="503"):
        asyncio.run(service.run_monitor_pending_episode(
            session, episode_id=episode.id, episode_slug=episode.slug, show_slug=show.slug,
            episode_identifier=episode.episode_identifier, episode_index=episode.index,
        ))
    session.close()
    engine.dispose()
