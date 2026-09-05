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


def test_recurring_episode_monitor_disables_task_retries(monkeypatch):
    from task_manager.tasks.workers.monitor_episode_worker import scheduling

    scheduler = FakeScheduler()
    monkeypatch.setattr(scheduling, "start_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        scheduling,
        "get_settings",
        lambda: SimpleNamespace(
            new_episode_schedule=SimpleNamespace(
                monitor_episode_cron="*/1 * * * *",
            ),
            timezone="Europe/Amsterdam",
        ),
    )

    scheduling.schedule_episode_monitor(
        show_slug="test-show",
        episode_slug="live-episode",
        season_id=11,
        episode_identifier="ep.101",
        episode_index=2,
        resource_id=501,
    )

    assert scheduler.job is not None
    assert scheduler.job["kwargs"]["max_retries"] == 0
    assert scheduler.job["max_instances"] == 1
    assert scheduler.job["coalesce"] is True


def _episode_record(slug: str):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{slug}",
        slug=slug,
        title="Live episode",
        description=None,
        duration=3600,
        episode_number="101.00",
        display_episode_number="101.00",
        background_image_path=None,
        sharing_url=f"https://example.test/{slug}",
        publish_status="LIVE",
        is_downloadable=False,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
        scheduled_date=None,
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
        uuid="show-uuid",
        slug="test-show",
        title="Test Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Test Host",
        author_slug="test-host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add_all([show, season])
    session.flush()

    episode = upsert_episode(
        session,
        show=show,
        season=season,
        ep=_episode_record("live-episode").model_copy(
            update={"publish_status": EpisodePublishStatus.LIVE.value},
            deep=True,
        ),
        index_value=2,
        ep_id="ep.101",
    )
    session.commit()
    return engine, session, show, episode


def test_monitor_marks_dailywire_404_as_dw_processing(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.helpers.episodes.processing import (
        DwProcessingReason,
        episode_dw_processing_reason,
        episode_dw_processing_since,
    )
    from task_manager.tasks.workers.monitor_episode_worker import service

    engine, session, show, episode = _monitor_fixture()

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == episode.slug
            assert require_member_exclusive is False
            raise MiddlewareAPIError(
                "HTTP error 404: episode not found",
                status_code=404,
            )

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)

    result = asyncio.run(
        service.run_monitor_episode_worker(
            session,
            episode_id=episode.id,
            episode_slug=episode.slug,
            show_slug=show.slug,
            episode_identifier=episode.episode_identifier,
            episode_index=episode.index,
        )
    )

    assert result is EpisodePublishStatus.DW_PROCESSING
    session.expire_all()
    stored = session.query(type(episode)).one()
    assert stored.publish_status == EpisodePublishStatus.DW_PROCESSING.value
    assert stored.metadata_is_final is False
    assert episode_dw_processing_reason(stored) is DwProcessingReason.NOT_FOUND
    first_seen = episode_dw_processing_since(stored)
    assert first_seen is not None

    # Another 404 is the same continuous incident and must not restart its age.
    asyncio.run(
        service.run_monitor_episode_worker(
            session,
            episode_id=stored.id,
            episode_slug=stored.slug,
            show_slug=show.slug,
            episode_identifier=stored.episode_identifier,
            episode_index=stored.index,
        )
    )
    session.expire_all()
    stored = session.query(type(episode)).one()
    assert episode_dw_processing_since(stored) == first_seen

    session.close()
    engine.dispose()


def test_monitor_still_raises_non_404_dailywire_errors(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.workers.monitor_episode_worker import service

    engine, session, show, episode = _monitor_fixture()

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("HTTP error 503", status_code=503)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)

    with pytest.raises(MiddlewareAPIError, match="503"):
        asyncio.run(
            service.run_monitor_episode_worker(
                session,
                episode_id=episode.id,
                episode_slug=episode.slug,
                show_slug=show.slug,
                episode_identifier=episode.episode_identifier,
                episode_index=episode.index,
            )
        )

    session.close()
    engine.dispose()
