from __future__ import annotations

import hashlib
import logging
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.cron import CronTrigger

from config import get_settings
from task_manager.events.registry import WireloftEventLinker
from task_manager.scheduler.executor import execute_task
from task_manager.scheduler.scheduler import start_scheduler


logger = logging.getLogger(__name__)

MONITOR_REQUESTED_EVENT = "episode.monitor_requested"
MONITOR_COMPLETED_EVENT = "episode.monitor_completed"


def monitor_job_id(show_slug: str, episode_identifier: str) -> str:
    """Return a stable, APScheduler-safe id for one logical episode monitor."""
    identity = f"{show_slug}\0{episode_identifier}".encode()
    digest = hashlib.sha256(identity).hexdigest()[:20]
    return f"auto-monitor-episode-{digest}"


def schedule_episode_monitor(
        *,
        show_slug: str,
        episode_slug: str,
        season_id: int,
        episode_identifier: str,
        episode_index: int,
        resource_id: int | None = None,
) -> str:
    """Create or refresh the recurring monitor job for one episode."""
    scheduler = start_scheduler()
    job_id = monitor_job_id(show_slug, episode_identifier)
    trigger = CronTrigger.from_crontab(
        get_settings().new_episode_schedule.monitor_episode_cron,
        timezone=get_settings().timezone,
    )
    scheduler.add_job(
        execute_task,
        trigger=trigger,
        kwargs={
            "def_key": "monitor_episode_worker",
            "resource_type": "episode",
            "resource_id": resource_id,
            "schedule_id": None,
            # The recurring cron schedule already is this worker's retry loop.
            # Generic TaskRun retries would create separate date jobs that can run
            # in between cron ticks and multiply one transient failure into many
            # concurrent monitor attempts.
            "max_retries": 0,
            "slug": episode_slug,
            "show_slug": show_slug,
            "season_id": season_id,
            "episode_identifier": episode_identifier,
            "episode_index": episode_index,
        },
        id=job_id,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        "Scheduled monitor job %s for %s (%s)",
        job_id,
        episode_slug,
        episode_identifier,
    )
    return job_id


def remove_episode_monitor(*, show_slug: str, episode_identifier: str) -> None:
    """Remove the recurring monitor job after the episode becomes final."""
    job_id = monitor_job_id(show_slug, episode_identifier)
    try:
        start_scheduler().remove_job(job_id)
        logger.info("Removed completed episode monitor job %s", job_id)
    except JobLookupError:
        # Completion is idempotent: the job may already have been removed during
        # shutdown or by an earlier completion event.
        pass


def _handle_monitor_requested(**event_data: Any) -> None:
    required = (
        "show_slug",
        "slug",
        "season_id",
        "episode_identifier",
        "episode_index",
    )
    missing = [key for key in required if event_data.get(key) is None]
    if missing:
        logger.error(
            "Cannot schedule episode monitor; event is missing: %s",
            ", ".join(missing),
        )
        return

    schedule_episode_monitor(
        show_slug=str(event_data["show_slug"]),
        episode_slug=str(event_data["slug"]),
        season_id=int(event_data["season_id"]),
        episode_identifier=str(event_data["episode_identifier"]),
        episode_index=int(event_data["episode_index"]),
        resource_id=event_data.get("resource_id"),
    )


def _handle_monitor_completed(**event_data: Any) -> None:
    show_slug = event_data.get("show_slug")
    episode_identifier = event_data.get("episode_identifier")
    if show_slug is None or episode_identifier is None:
        logger.error("Cannot remove episode monitor; completion event is incomplete")
        return

    remove_episode_monitor(
        show_slug=str(show_slug),
        episode_identifier=str(episode_identifier),
    )


def register_monitor_event_handlers() -> None:
    """Wire system-level monitor lifecycle events into APScheduler."""
    WireloftEventLinker.subscribe(
        MONITOR_REQUESTED_EVENT,
        event_callback=_handle_monitor_requested,
    )
    WireloftEventLinker.subscribe(
        MONITOR_COMPLETED_EVENT,
        event_callback=_handle_monitor_completed,
    )
