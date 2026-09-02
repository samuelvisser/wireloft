from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


def test_metadata_refresh_interval_parser_normalizes_and_validates():
    from config.settings.submodels import (
        normalize_metadata_refresh_intervals,
        parse_metadata_refresh_intervals,
    )

    value = "5m, 15m,30m,1h,3h,6h,24h"
    assert normalize_metadata_refresh_intervals(value) == "5m,15m,30m,1h,3h,6h,24h"
    assert parse_metadata_refresh_intervals(value) == (
        300,
        900,
        1800,
        3600,
        10800,
        21600,
        86400,
    )

    with pytest.raises(ValueError, match="strictly increasing"):
        parse_metadata_refresh_intervals("5m,1h,30m")
    with pytest.raises(ValueError, match="strictly increasing"):
        parse_metadata_refresh_intervals("60m,1h")
    with pytest.raises(ValueError, match="positive"):
        parse_metadata_refresh_intervals("5m,soon")


def test_app_settings_exposes_default_metadata_refresh_intervals():
    from config.settings.settings import AppSettings

    assert (
        AppSettings().new_episode_schedule.metadata_refresh_intervals
        == "5m,15m,30m,1h,3h,6h,24h"
    )


def test_new_episode_metadata_finality_uses_last_interval(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import metadata

    monkeypatch.setattr(
        metadata,
        "metadata_refresh_offsets_seconds",
        lambda: (300, 900, 1800, 3600, 10800, 21600, 86400),
    )
    now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)

    assert metadata.metadata_is_final_for_new_episode(
        EpisodePublishStatus.LIVE,
        now - timedelta(days=2),
        now=now,
    ) is False
    assert metadata.metadata_is_final_for_new_episode(
        EpisodePublishStatus.PUBLISHED_FINAL,
        now - timedelta(hours=23),
        now=now,
    ) is False
    assert metadata.metadata_is_final_for_new_episode(
        EpisodePublishStatus.PUBLISHED_FINAL,
        now - timedelta(hours=25),
        now=now,
    ) is True


def test_remaining_metadata_checks_are_anchored_to_publish_time(monkeypatch):
    from task_manager.tasks.workers.refresh_episode_metadata_worker import scheduling

    class FakeScheduler:
        def __init__(self):
            self.jobs = {}

        def add_job(self, function, **kwargs):
            job_id = kwargs["id"]
            self.jobs[job_id] = SimpleNamespace(function=function, **kwargs)

    scheduler = FakeScheduler()
    monkeypatch.setattr(scheduling, "start_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        scheduling,
        "metadata_refresh_offsets_seconds",
        lambda: (300, 900, 1800, 3600, 10800, 21600, 86400),
    )

    published_at = datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
    now = published_at + timedelta(hours=1, minutes=30)
    job_ids = scheduling.schedule_remaining_metadata_checks(
        episode_id=42,
        published_date=published_at,
        now=now,
    )

    assert job_ids == [
        scheduling.metadata_job_id(42, 10800),
        scheduling.metadata_job_id(42, 21600),
        scheduling.metadata_job_id(42, 86400),
    ]
    assert {
        job.kwargs["scheduled_offset_seconds"]
        for job in scheduler.jobs.values()
    } == {10800, 21600, 86400}


def test_metadata_worker_uses_registry_trigger_metadata():
    import inspect
    import task_manager.tasks  # noqa: F401
    from task_manager.scheduler.registry import get_task
    from task_manager.tasks.helpers.episodes.metadata import METADATA_REFRESH_REQUESTED_EVENT
    from task_manager.tasks.workers.monitor_episode_worker.scheduling import MONITOR_COMPLETED_EVENT

    meta, worker = get_task("refresh_episode_metadata_worker")
    events = {
        trigger.event_name
        for trigger in meta.triggers
        if trigger.trigger_type == "event"
    }

    assert events == {
        "app.startup",
        METADATA_REFRESH_REQUESTED_EVENT,
        MONITOR_COMPLETED_EVENT,
    }
    parameters = inspect.signature(worker).parameters
    assert "manual_request_id" in parameters
    assert "manual_request_ids" in parameters


def test_pending_manual_metadata_refresh_requests_persist_until_completed():
    from backend.utils.episode import (
        add_pending_manual_metadata_refresh_request,
        complete_manual_metadata_refresh_requests,
        pending_manual_metadata_refresh_request_ids,
    )

    class FakeEpisode:
        def __init__(self):
            self.meta: dict[str, str | None] = {}

        def get_meta(self, key: str):
            return self.meta.get(key)

        def set_meta(self, key: str, value: str | None):
            self.meta[key] = value

    episode = FakeEpisode()
    add_pending_manual_metadata_refresh_request(episode, "request-a")
    add_pending_manual_metadata_refresh_request(episode, "request-b")
    add_pending_manual_metadata_refresh_request(episode, "request-a")

    assert pending_manual_metadata_refresh_request_ids(episode) == (
        "request-a",
        "request-b",
    )

    complete_manual_metadata_refresh_requests(episode, ("request-b",))
    assert pending_manual_metadata_refresh_request_ids(episode) == ("request-a",)

    complete_manual_metadata_refresh_requests(episode, ("request-a",))
    assert pending_manual_metadata_refresh_request_ids(episode) == ()


def test_manual_episode_metadata_refresh_marks_unfinished_and_queues_worker(monkeypatch):
    from backend.api.endpoints.episodes import service

    request_id = "episode-refresh-request"
    episode = SimpleNamespace(
        id=17,
        slug="test-episode",
        show_id=3,
        metadata_is_final=True,
    )
    queued: list[tuple[str, dict]] = []
    persisted_request_ids: list[str] = []

    class Query:
        def filter_by(self, **kwargs):
            assert kwargs == {"slug": episode.slug}
            return self

        def one_or_none(self):
            return episode

    class FakeSession:
        def __init__(self):
            self.flushes = 0

        def query(self, model):
            return Query()

        def flush(self):
            self.flushes += 1

    session = FakeSession()
    monkeypatch.setattr(service, "uuid4", lambda: request_id)
    monkeypatch.setattr(
        service,
        "add_pending_manual_metadata_refresh_request",
        lambda item, value: persisted_request_ids.append(value),
    )
    monkeypatch.setattr(
        service,
        "queue_event",
        lambda _session, name, payload: queued.append((name, payload)),
    )

    result = service.request_episode_metadata_refresh(session, episode.slug)

    assert result == {
        "queued": True,
        "episode_id": episode.id,
        "request_id": request_id,
    }
    assert episode.metadata_is_final is False
    assert persisted_request_ids == [request_id]
    assert session.flushes == 1
    assert queued == [(
        service.METADATA_REFRESH_REQUESTED_EVENT,
        {
            "resource_id": episode.id,
            "id": episode.id,
            "slug": episode.slug,
            "show_id": episode.show_id,
            "refresh": True,
            "manual_request_id": request_id,
        },
    )]


def test_show_metadata_refresh_marks_every_episode_through_shared_helper(monkeypatch):
    from backend.api.endpoints.shows import service
    from backend.db.models import Episode, Show

    request_id = "show-refresh-request"
    show = SimpleNamespace(id=9, slug="test-show")
    episodes = [
        SimpleNamespace(id=1, metadata_is_final=True),
        SimpleNamespace(id=2, metadata_is_final=True),
        SimpleNamespace(id=3, metadata_is_final=False),
    ]
    queued: list[tuple[int, str | None]] = []

    class Query:
        def __init__(self, model):
            self.model = model

        def filter_by(self, **kwargs):
            if self.model is Show:
                assert kwargs == {"slug": show.slug}
            elif self.model is Episode:
                assert kwargs == {"show_id": show.id}
            return self

        def one_or_none(self):
            assert self.model is Show
            return show

        def all(self):
            assert self.model is Episode
            return episodes

    class FakeSession:
        def __init__(self):
            self.flushes = 0

        def query(self, model):
            return Query(model)

        def flush(self):
            self.flushes += 1

    def queue_refresh(_session, episode, *, manual_request_id=None):
        episode.metadata_is_final = False
        queued.append((episode.id, manual_request_id))

    session = FakeSession()
    monkeypatch.setattr(service, "uuid4", lambda: request_id)
    monkeypatch.setattr(service, "queue_episode_metadata_refresh", queue_refresh)

    result = service.request_show_metadata_refresh(session, show.slug)

    assert result == {
        "queued": True,
        "episodes_queued": 3,
        "request_id": request_id,
    }
    assert queued == [
        (1, request_id),
        (2, request_id),
        (3, request_id),
    ]
    assert all(episode.metadata_is_final is False for episode in episodes)
    assert session.flushes == 1


def test_manual_request_id_filters_normal_and_recovery_task_runs(monkeypatch):
    from backend.api.endpoints.tasks import service

    def task_run(run_id: int, inputs: dict):
        return SimpleNamespace(
            id=run_id,
            resource_type="episode",
            resource_id=run_id,
            status="SUCCEEDED",
            progress=100,
            message="OK",
            attempt_count=1,
            max_retries=5,
            last_error=None,
            started_at=datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
            finished_at=datetime(2026, 9, 2, 12, 0, 1, tzinfo=timezone.utc),
            runtime_ms=1000,
            meta={"inputs": inputs},
        )

    direct = task_run(1, {"manual_request_id": "wanted"})
    recovered = task_run(2, {"manual_request_ids": ["other", "wanted"]})
    other = task_run(3, {"manual_request_id": "other"})

    class Result:
        def all(self):
            return [
                (direct, "refresh_episode_metadata_worker"),
                (recovered, "refresh_episode_metadata_worker"),
                (other, "refresh_episode_metadata_worker"),
            ]

    class FakeSession:
        def execute(self, statement):
            return Result()

        def close(self):
            pass

    monkeypatch.setattr(service, "get_session", FakeSession)

    result = service.list_runs(
        definition_key="refresh_episode_metadata_worker",
        manual_request_id="wanted",
    )

    assert [row["id"] for row in result] == [direct.id, recovered.id]


def test_startup_recovery_preserves_pending_manual_request_ids(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.workers.refresh_episode_metadata_worker import service

    final_episode = SimpleNamespace(
        id=31,
        publish_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
    )
    live_episode = SimpleNamespace(
        id=32,
        publish_status=EpisodePublishStatus.LIVE.value,
    )
    live_without_manual_request = SimpleNamespace(
        id=33,
        publish_status=EpisodePublishStatus.LIVE.value,
    )

    class ScalarResult:
        def __iter__(self):
            return iter((final_episode, live_episode, live_without_manual_request))

    class FakeSession:
        def scalars(self, statement):
            return ScalarResult()

    queued: list[dict] = []
    monkeypatch.setattr(
        service,
        "pending_manual_metadata_refresh_request_ids",
        lambda episode: ("request-a", "request-b") if episode.id == live_episode.id else (),
    )
    monkeypatch.setattr(
        service,
        "trigger_now",
        lambda **kwargs: queued.append(kwargs),
    )

    service._queue_startup_recovery(FakeSession())

    assert queued == [
        {
            "def_key": "refresh_episode_metadata_worker",
            "resource_type": "episode",
            "resource_id": final_episode.id,
            "refresh": True,
        },
        {
            "def_key": "refresh_episode_metadata_worker",
            "resource_type": "episode",
            "resource_id": live_episode.id,
            "refresh": True,
            "manual_request_ids": ["request-a", "request-b"],
        },
    ]


def test_manual_metadata_refresh_fetches_non_final_episode_and_completes_request(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.workers.refresh_episode_metadata_worker import service

    episode = SimpleNamespace(
        id=21,
        metadata_is_final=False,
        publish_status=EpisodePublishStatus.LIVE.value,
    )
    refreshed: list[int] = []
    completed: list[tuple[str, ...]] = []

    class FakeSession:
        def __init__(self):
            self.commits = 0

        def get(self, model, episode_id):
            assert episode_id == episode.id
            return episode

        def commit(self):
            self.commits += 1

    session = FakeSession()
    monkeypatch.setattr(
        service,
        "_refresh_episode_from_dailywire",
        lambda _session, item: refreshed.append(item.id),
    )
    monkeypatch.setattr(
        service,
        "complete_manual_metadata_refresh_requests",
        lambda item, request_ids: completed.append(tuple(request_ids)),
    )

    asyncio.run(
        service.run_refresh_episode_metadata_worker(
            session,
            episode_id=episode.id,
            refresh=True,
            manual_request_ids=("request-a",),
        )
    )

    assert refreshed == [episode.id]
    assert completed == [("request-a",)]
    assert episode.metadata_is_final is False
    assert session.commits == 1
