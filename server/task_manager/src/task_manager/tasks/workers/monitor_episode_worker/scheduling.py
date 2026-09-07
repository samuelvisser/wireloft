from __future__ import annotations

import logging
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.episode_types import EpisodePublishStatus
from config import get_settings
from task_manager.events.registry import WireloftEventLinker
from task_manager.events.transactional import queue_event
from task_manager.scheduler.executor import execute_task
from task_manager.scheduler.scheduler import start_scheduler
from ...helpers.episodes.events import episode_event_payload


logger = logging.getLogger(__name__)

MONITOR_REQUESTED_EVENT = "episode.monitor_requested"
MONITOR_COMPLETED_EVENT = "episode.monitor_completed"


def monitor_job_id(resource_id: int) -> str:
    """Return the stable APScheduler id for one episode monitor."""
    return f"auto-monitor-episode-{resource_id}"


def schedule_episode_monitor(*, resource_id: int) -> str:
    """Create or refresh the recurring monitor job for one episode."""
    scheduler = start_scheduler()
    job_id = monitor_job_id(resource_id)
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
            "max_retries": 0,
        },
        id=job_id,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("Scheduled monitor job %s for episode %s", job_id, resource_id)
    return job_id


def remove_episode_monitor(*, resource_id: int) -> None:
    """Remove the recurring monitor job after the episode becomes final."""
    job_id = monitor_job_id(resource_id)
    try:
        start_scheduler().remove_job(job_id)
        logger.info("Removed completed episode monitor job %s", job_id)
    except JobLookupError:
        # Completion is idempotent: the job may already have been removed during
        # shutdown or by an earlier completion event.
        pass


def queue_monitor_completion_if_settled(
        s: Session,
        *,
        episode: Episode,
        show: Show,
        old_status: str | None,
) -> bool:
    """Queue monitor completion when this episode no longer needs polling.

    Scheduler identity is based on the immutable local episode id. Metadata such as
    the Daily Wire slug or WireLoft episode identifier may change while a monitor is
    active without requiring the APScheduler job to be re-keyed.
    """
    should_continue = (
        episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value
        and not episode.is_no_show_today
    )
    if should_continue:
        return False

    queue_event(
        s,
        MONITOR_COMPLETED_EVENT,
        episode_event_payload(
            episode=episode,
            show=show,
            old_status=old_status,
        ),
    )
    return True


def _handle_monitor_requested(**event_data: Any) -> None:
    resource_id = event_data.get("resource_id")
    if resource_id is None:
        logger.error("Cannot schedule episode monitor; event is missing resource_id")
        return

    schedule_episode_monitor(resource_id=int(resource_id))


def _handle_monitor_completed(**event_data: Any) -> None:
    resource_id = event_data.get("resource_id")
    if resource_id is None:
        logger.error("Cannot remove episode monitor; completion event is missing resource_id")
        return

    remove_episode_monitor(resource_id=int(resource_id))


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
