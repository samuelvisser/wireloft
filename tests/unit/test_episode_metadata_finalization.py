from __future__ import annotations

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
    import task_manager.tasks  # noqa: F401
    from task_manager.scheduler.registry import get_task
    from task_manager.tasks.helpers.episodes.metadata import METADATA_REFRESH_REQUESTED_EVENT
    from task_manager.tasks.workers.monitor_episode_worker.scheduling import MONITOR_COMPLETED_EVENT

    meta, _worker = get_task("refresh_episode_metadata_worker")
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
