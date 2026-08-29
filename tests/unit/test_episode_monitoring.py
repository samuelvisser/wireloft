from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    def add_job(self, function, **kwargs):
        self.jobs[kwargs["id"]] = {"function": function, **kwargs}

    def remove_job(self, job_id: str):
        from apscheduler.jobstores.base import JobLookupError

        if job_id not in self.jobs:
            raise JobLookupError(job_id)
        del self.jobs[job_id]


def _monitor_event(
        *,
        slug: str,
        identifier: str,
        episode_index: int,
        resource_id: int | None = None,
) -> dict:
    return {
        "resource_id": resource_id,
        "slug": slug,
        "show_id": 1,
        "show_slug": "test-show",
        "season_id": 11,
        "episode_identifier": identifier,
        "episode_index": episode_index,
        "status": "live",
    }


def test_monitor_events_create_independent_idempotent_cron_jobs(monkeypatch):
    from task_manager.events.emitters import emit_event
    from task_manager.events.registry import wait_for_events
    from task_manager.tasks.workers.monitor_episode_worker import scheduling

    scheduler = FakeScheduler()
    monkeypatch.setattr(scheduling, "start_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        scheduling,
        "get_settings",
        lambda: SimpleNamespace(
            new_episode_schedule=SimpleNamespace(
                monitor_episode_cron="*/7 * * * *",
            ),
            timezone="Europe/Amsterdam",
        ),
    )
    scheduling.register_monitor_event_handlers()

    first = _monitor_event(
        slug="live-one",
        identifier="ep.100",
        episode_index=100,
    )
    second = _monitor_event(
        slug="live-two",
        identifier="ep.101",
        episode_index=101,
    )
    emit_event(scheduling.MONITOR_REQUESTED_EVENT, first)
    emit_event(scheduling.MONITOR_REQUESTED_EVENT, second)
    wait_for_events()

    first_job_id = scheduling.monitor_job_id("test-show", "ep.100")
    second_job_id = scheduling.monitor_job_id("test-show", "ep.101")
    assert set(scheduler.jobs) == {first_job_id, second_job_id}
    assert scheduler.jobs[first_job_id]["max_instances"] == 1
    assert scheduler.jobs[first_job_id]["coalesce"] is True
    assert "minute='*/7'" in str(scheduler.jobs[first_job_id]["trigger"])
    assert (
        scheduler.jobs[first_job_id]["kwargs"]["slug"]
        == "live-one"
    )

    # A later fetch refreshes the same logical job and can attach its local id.
    emit_event(
        scheduling.MONITOR_REQUESTED_EVENT,
        {**first, "resource_id": 501},
    )
    wait_for_events()
    assert len(scheduler.jobs) == 2
    assert (
        scheduler.jobs[first_job_id]["kwargs"]["resource_id"]
        == 501
    )

    emit_event(
        scheduling.MONITOR_COMPLETED_EVENT,
        {
            "show_slug": "test-show",
            "episode_identifier": "ep.100",
        },
    )
    wait_for_events()
    assert set(scheduler.jobs) == {second_job_id}


def _episode_record(
        slug: str,
        episode_number: str,
        published_at: datetime,
        *,
        status: str = "LIVE",
):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{slug}",
        slug=slug,
        title=f"Episode {episode_number}",
        description=None,
        duration=3600,
        episode_number=episode_number,
        display_episode_number=episode_number,
        background_image_path=None,
        sharing_url=f"https://example.test/{slug}",
        publish_status=status,
        is_downloadable=False,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=published_at,
        scheduled_date=None,
    )


def test_mapper_does_not_reidentify_an_existing_non_final_episode():
    from dailywire_api.dw_api.client import EpisodesPaginatedResult
    from task_manager.tasks.helpers.episodes.mapper import (
        get_dw_episodes_since_ep,
    )
    from task_manager.tasks.types.general import RecordOrder

    cursor = _episode_record(
        "final-cursor",
        "100.00",
        datetime(2026, 7, 22, 10, tzinfo=timezone.utc),
        status="PUBLISHED",
    )
    existing_live = _episode_record(
        "known-live",
        "101.00",
        datetime(2026, 7, 22, 11, tzinfo=timezone.utc),
    )
    new_live = _episode_record(
        "new-live",
        "102.00",
        datetime(2026, 7, 22, 12, tzinfo=timezone.utc),
    )

    class FakeClient:
        def get_episodes_paginated(self, show_slug, selector):
            return EpisodesPaginatedResult(
                [new_live, existing_live, cursor],
                None,
                False,
            )

    season = SimpleNamespace(id=11, index=1, slug="season-1", name="One")
    show = SimpleNamespace(slug="test-show", episode_identifier="numbered")
    since_episode = SimpleNamespace(slug=cursor.slug, season=season)

    episode_map, identifier_values = get_dw_episodes_since_ep(
        FakeClient(),
        show=show,
        membership_plan="FREE",
        seasons=[season],
        dw_id_by_slug={"season-1": "remote-season"},
        known_episode_slugs={"known-live"},
        since_episode=since_episode,
        prev_max_values={"ep_id.latest_ep_num": 100},
        order=RecordOrder.ASC,
    )

    assert [
        (identifier, episode.slug)
        for identifier, episode in episode_map[season.id]
    ] == [("ep.102", "new-live")]
    assert identifier_values["ep_id.latest_ep_num"] == 102


def _episode_detail(slug: str, episode_number: str = "103.00", *, status: str = "LIVE"):
    from dailywire_api.records import DwEpisodeDetailRecord

    return DwEpisodeDetailRecord(
        **_episode_record(
            slug,
            episode_number,
            datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
            status=status,
        ).model_dump(mode="python", by_alias=False),
        audio_url="https://example.test/audio.mp3",
        video_url="https://example.test/video.m3u8",
        delivery_mode="VOD",
        progress=0,
        next_episode_url=None,
        playback_status=None,
    )


def _make_show_and_season(session):
    from backend.db.models import Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

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
    session.commit()
    return show, season


def test_monitor_updates_and_completes_one_episode(monkeypatch):
    from backend.db import Base
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import events as episode_events
    from task_manager.tasks.helpers.episodes.save import upsert_episode
    from task_manager.tasks.workers.monitor_episode_worker import service
    from task_manager.tasks.workers.monitor_episode_worker.scheduling import (
        MONITOR_COMPLETED_EVENT,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show, season = _make_show_and_season(session)

    detail = _episode_detail("live-episode")

    # fetch_new_episodes indexes the episode before any monitor runs
    upsert_episode(
        session,
        show=show,
        season=season,
        ep=_episode_record(
            detail.slug,
            "103.00",
            datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
        ).model_copy(
            update={"publish_status": EpisodePublishStatus.SCHEDULED.value},
            deep=True,
        ),
        index_value=1,
        ep_id="ep.103",
    )
    session.commit()

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == detail.slug
            assert require_member_exclusive is False
            return detail

    statuses = iter(
        [
            EpisodePublishStatus.LIVE,
            EpisodePublishStatus.PUBLISHED_FINAL,
        ]
    )
    queued = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    monkeypatch.setattr(
        service,
        "get_publish_status_from_dw_detail",
        lambda episode: next(statuses),
    )
    monkeypatch.setattr(service, "queue_event", queued)
    monkeypatch.setattr(episode_events, "queue_event", queued)

    result = asyncio.run(
        service.run_monitor_episode_worker(
            session,
            episode_slug=detail.slug,
            show_slug=show.slug,
            season_id=season.id,
            episode_identifier="ep.103",
            episode_index=1,
        )
    )
    assert result is EpisodePublishStatus.LIVE

    episode = session.query(Episode).one()
    episode_id = episode.id
    assert episode.publish_status == EpisodePublishStatus.LIVE.value
    assert episode.episode_identifier == "ep.103"
    assert episode.index == 1
    event_names = [call.args[1] for call in queued.call_args_list]
    assert "episode.status_updated" in event_names
    assert "episode.added" not in event_names
    assert MONITOR_COMPLETED_EVENT not in event_names

    queued.reset_mock()
    result = asyncio.run(
        service.run_monitor_episode_worker(
            session,
            episode_id=episode_id,
            episode_slug=detail.slug,
            show_slug=show.slug,
            season_id=season.id,
            episode_identifier="ep.103",
            episode_index=1,
        )
    )
    assert result is EpisodePublishStatus.PUBLISHED_FINAL

    session.expire_all()
    episode = session.query(Episode).one()
    assert episode.id == episode_id
    assert episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
    event_names = [call.args[1] for call in queued.call_args_list]
    assert "episode.published_final" in event_names
    assert MONITOR_COMPLETED_EVENT in event_names

    session.close()
    engine.dispose()


def test_monitor_refuses_unindexed_episode(monkeypatch):
    import pytest

    from backend.db import Base
    from task_manager.tasks.workers.monitor_episode_worker import service

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show, season = _make_show_and_season(session)

    with pytest.raises(ValueError, match="not found in database"):
        asyncio.run(
            service.run_monitor_episode_worker(
                session,
                episode_slug="never-indexed",
                show_slug=show.slug,
                season_id=season.id,
                episode_identifier="ep.999",
                episode_index=1,
            )
        )

    session.close()
    engine.dispose()


def _fetch_test_fixture(session):
    """A show with one final cursor episode (ep.100) already indexed."""
    from backend.db.models import Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from task_manager.tasks.helpers.episodes.save import upsert_episode

    show = Show(
        uuid="fetch-show-uuid",
        slug="fetch-test-show",
        title="Fetch Test Show",
        description=None,
        sharing_url="https://example.test/fetch-show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Test Host",
        author_slug="test-host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    session.add_all([show, season])
    session.flush()

    cursor = _episode_record(
        "final-cursor",
        "100.00",
        datetime(2026, 7, 21, 10, tzinfo=timezone.utc),
        status="PUBLISHED",
    )
    upsert_episode(
        session,
        show=show,
        season=season,
        ep=cursor.model_copy(
            update={"publish_status": "published_final"},
            deep=True,
        ),
        index_value=1,
        ep_id="ep.100",
    )
    show.set_meta("ep_id.latest_ep_num", "100")
    session.commit()
    return show, season, cursor


def _fetch_fakes(season, remote_episodes, detail_by_slug):
    from dailywire_api.dw_api.client import EpisodesPaginatedResult

    class FakeDeviceAuthClient:
        def get_token(self):
            return None

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_show_page(self, slug, *, membership_plan):
            return SimpleNamespace(
                seasons=[
                    SimpleNamespace(
                        slug=season.slug,
                        dw_id="remote-season",
                    )
                ]
            )

        def get_episodes_paginated(self, show_slug, selector):
            return EpisodesPaginatedResult(list(remote_episodes), None, False)

        def get_episode_details(self, slug, *, require_member_exclusive):
            assert require_member_exclusive is False
            return detail_by_slug[slug]

    return FakeDeviceAuthClient, FakeClient


def test_fetch_saves_non_final_episode_and_requests_monitor(monkeypatch):
    from backend.db import Base
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import events as episode_events
    from task_manager.tasks.workers.fetch_new_episodes import service
    from task_manager.tasks.workers.monitor_episode_worker.scheduling import (
        MONITOR_REQUESTED_EVENT,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show, season, cursor = _fetch_test_fixture(session)

    live = _episode_record(
        "live-episode",
        "101.00",
        datetime(2026, 7, 23, 10, tzinfo=timezone.utc),
    )
    live_detail = _episode_detail(live.slug, "101.00")

    fake_auth, fake_client = _fetch_fakes(
        season, [live, cursor], {live.slug: live_detail}
    )
    queued = Mock()
    monkeypatch.setattr(service, "DeviceAuthClient", fake_auth)
    monkeypatch.setattr(service, "MiddlewareClient", fake_client)
    monkeypatch.setattr(service, "queue_event", queued)
    monkeypatch.setattr(episode_events, "queue_event", queued)

    asyncio.run(
        service.run_fetch_new_episodes(
            session,
            show_slug=show.slug,
        )
    )

    # The non-final episode is indexed immediately, with its real remote status
    episode = (
        session.query(Episode)
        .filter(Episode.slug == live.slug)
        .one()
    )
    assert episode.publish_status == EpisodePublishStatus.LIVE.value
    assert episode.episode_identifier == "ep.101"
    assert episode.index == 2
    assert episode.season_id == season.id

    event_names = [call.args[1] for call in queued.call_args_list]
    assert "episode.added" in event_names
    assert service.SHOW_INDEXED_EVENT in event_names

    indexed_call = next(
        call
        for call in queued.call_args_list
        if call.args[1] == service.SHOW_INDEXED_EVENT
    )
    assert indexed_call.args[2] == {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
        "indexed_count": 1,
    }

    monitor_calls = [
        call
        for call in queued.call_args_list
        if call.args[1] == MONITOR_REQUESTED_EVENT
    ]
    assert len(monitor_calls) == 1
    payload = monitor_calls[0].args[2]
    assert payload["resource_id"] == episode.id
    assert payload["slug"] == live.slug
    assert payload["show_slug"] == show.slug
    assert payload["season_id"] == season.id
    assert payload["episode_identifier"] == "ep.101"
    assert payload["episode_index"] == 2

    assert show.get_meta("ep_id.latest_ep_num") == "101"

    session.close()
    engine.dispose()


def test_fetch_rerun_requeues_monitor_without_reidentifying(monkeypatch):
    from backend.db import Base
    from backend.db.models import Episode
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import events as episode_events
    from task_manager.tasks.workers.fetch_new_episodes import service
    from task_manager.tasks.workers.monitor_episode_worker.scheduling import (
        MONITOR_REQUESTED_EVENT,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show, season, cursor = _fetch_test_fixture(session)

    live = _episode_record(
        "live-episode",
        "101.00",
        datetime(2026, 7, 23, 10, tzinfo=timezone.utc),
    )
    live_detail = _episode_detail(live.slug, "101.00")

    fake_auth, fake_client = _fetch_fakes(
        season, [live, cursor], {live.slug: live_detail}
    )
    queued = Mock()
    monkeypatch.setattr(service, "DeviceAuthClient", fake_auth)
    monkeypatch.setattr(service, "MiddlewareClient", fake_client)
    monkeypatch.setattr(service, "queue_event", queued)
    monkeypatch.setattr(episode_events, "queue_event", queued)

    asyncio.run(service.run_fetch_new_episodes(session, show_slug=show.slug))
    queued.reset_mock()

    # Second run: same remote state. The still-live episode must keep its row,
    # identifier and index, and its monitor must be requested again (monitor jobs
    # are in-memory only, so a fetch after a restart has to restore them).
    asyncio.run(service.run_fetch_new_episodes(session, show_slug=show.slug))

    episodes = (
        session.query(Episode)
        .filter(Episode.show_id == show.id)
        .order_by(Episode.index)
        .all()
    )
    assert [(e.episode_identifier, e.slug) for e in episodes] == [
        ("ep.100", cursor.slug),
        ("ep.101", live.slug),
    ]
    assert episodes[1].publish_status == EpisodePublishStatus.LIVE.value
    assert show.get_meta("ep_id.latest_ep_num") == "101"
    assert show.get_meta("ep_id.latest_aux_num") == "0"

    monitor_calls = [
        call
        for call in queued.call_args_list
        if call.args[1] == MONITOR_REQUESTED_EVENT
    ]
    assert len(monitor_calls) == 1
    payload = monitor_calls[0].args[2]
    assert payload["resource_id"] == episodes[1].id
    assert payload["episode_identifier"] == "ep.101"

    indexed_calls = [
        call
        for call in queued.call_args_list
        if call.args[1] == service.SHOW_INDEXED_EVENT
    ]
    assert len(indexed_calls) == 1
    assert indexed_calls[0].args[2]["resource_id"] == show.id
    assert indexed_calls[0].args[2]["indexed_count"] == 0

    session.close()
    engine.dispose()
