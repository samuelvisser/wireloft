from __future__ import annotations

import logging
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from config import get_settings
from task_manager.events.registry import WireloftEventLinker
from task_manager.events.transactional import queue_event
from task_manager.scheduler.executor import execute_task
from task_manager.scheduler.scheduler import start_scheduler
from ...helpers.episodes.events import episode_event_payload
from ...helpers.episodes.same_episode import PENDING_EPISODE_STATUSES


logger = logging.getLogger(__name__)

MONITOR_REQUESTED_EVENT = "episode.monitor_requested"
MONITOR_COMPLETED_EVENT = "episode.monitor_completed"


def monitor_job_id(resource_id: int) -> str:
    return f"auto-monitor-episode-{resource_id}"


def schedule_episode_monitor(*, resource_id: int) -> str:
    scheduler = start_scheduler()
    job_id = monitor_job_id(resource_id)
    trigger = CronTrigger.from_crontab(
        get_settings().new_episode_schedule.monitor_pending_episode_cron,
        timezone=get_settings().timezone,
    )
    scheduler.add_job(
        execute_task,
        trigger=trigger,
        kwargs={
            "def_key": "monitor_pending_episode",
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
    logger.info("Scheduled pending monitor job %s for episode %s", job_id, resource_id)
    return job_id


def remove_episode_monitor(*, resource_id: int) -> None:
    job_id = monitor_job_id(resource_id)
    try:
        start_scheduler().remove_job(job_id)
        logger.info("Removed pending episode monitor job %s", job_id)
    except JobLookupError:
        pass


def queue_monitor_completion_if_settled(
    s: Session,
    *,
    episode: Episode,
    show: Show,
    old_status: str | None,
) -> bool:
    if episode.publish_status in PENDING_EPISODE_STATUSES:
        return False
    queue_event(
        s,
        MONITOR_COMPLETED_EVENT,
        episode_event_payload(episode=episode, show=show, old_status=old_status),
    )
    return True


def _handle_monitor_requested(**event_data: Any) -> None:
    resource_id = event_data.get("resource_id")
    if resource_id is None:
        logger.error("Cannot schedule pending episode monitor; event is missing resource_id")
        return
    schedule_episode_monitor(resource_id=int(resource_id))


def _handle_monitor_completed(**event_data: Any) -> None:
    resource_id = event_data.get("resource_id")
    if resource_id is None:
        logger.error("Cannot remove pending episode monitor; event is missing resource_id")
        return
    remove_episode_monitor(resource_id=int(resource_id))


def register_monitor_event_handlers() -> None:
    WireloftEventLinker.subscribe(MONITOR_REQUESTED_EVENT, event_callback=_handle_monitor_requested)
    WireloftEventLinker.subscribe(MONITOR_COMPLETED_EVENT, event_callback=_handle_monitor_completed)
