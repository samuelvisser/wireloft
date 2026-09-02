from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.date import DateTrigger

from task_manager.scheduler.executor import execute_task
from task_manager.scheduler.scheduler import start_scheduler
from ...helpers.episodes.metadata import ensure_utc, metadata_refresh_offsets_seconds


logger = logging.getLogger(__name__)
_TASK_KEY = "refresh_episode_metadata_worker"
_JOB_PREFIX = "auto-refresh-episode-metadata"


def metadata_job_id(episode_id: int, offset_seconds: int) -> str:
    return f"{_JOB_PREFIX}-{episode_id}-{offset_seconds}"


def schedule_remaining_metadata_checks(
        *,
        episode_id: int,
        published_date: datetime | None,
        now: datetime | None = None,
) -> list[str]:
    """Schedule every configured metadata check whose publication offset is future."""
    if published_date is None:
        return []

    scheduler = start_scheduler()
    published_at = ensure_utc(published_date)
    current = ensure_utc(now or datetime.now(timezone.utc))
    job_ids: list[str] = []

    for offset_seconds in metadata_refresh_offsets_seconds():
        run_at = published_at + timedelta(seconds=offset_seconds)
        if run_at <= current:
            continue

        job_id = metadata_job_id(episode_id, offset_seconds)
        scheduler.add_job(
            execute_task,
            trigger=DateTrigger(run_date=run_at),
            kwargs={
                "def_key": _TASK_KEY,
                "resource_type": "episode",
                "resource_id": episode_id,
                "schedule_id": None,
                "refresh": True,
                "scheduled_offset_seconds": offset_seconds,
            },
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            # If the process is alive but temporarily too busy to start the exact
            # DateTrigger on time, the metadata check should still happen late.
            misfire_grace_time=None,
        )
        job_ids.append(job_id)

    if job_ids:
        logger.info(
            "Scheduled %s metadata refresh(es) for episode %s",
            len(job_ids),
            episode_id,
        )
    return job_ids


def remove_episode_metadata_jobs(episode_id: int) -> None:
    """Remove any still-pending metadata jobs after the episode is finalized."""
    scheduler = start_scheduler()
    prefix = f"{_JOB_PREFIX}-{episode_id}-"
    for job in scheduler.get_jobs():
        if not job.id.startswith(prefix):
            continue
        try:
            scheduler.remove_job(job.id)
        except JobLookupError:
            pass
