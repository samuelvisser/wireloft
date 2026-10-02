from __future__ import annotations

from datetime import datetime

from apscheduler.triggers.date import DateTrigger

from task_manager.scheduler.executor import execute_task
from task_manager.scheduler.scheduler import start_scheduler


_TASK_KEY = "download_profile_worker"
_JOB_PREFIX = "auto-download-episode"


def schedule_delayed_episode_download(*, episode_id: int, run_at: datetime) -> str:
    """Schedule the normal Download Profile worker for the episode eligibility time."""
    scheduler = start_scheduler()
    job_id = f"{_JOB_PREFIX}-{episode_id}"
    scheduler.add_job(
        execute_task,
        trigger=DateTrigger(run_date=run_at),
        kwargs={
            "def_key": _TASK_KEY,
            "resource_type": "episode",
            "resource_id": episode_id,
            "schedule_id": None,
        },
        id=job_id,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=None,
    )
    return job_id
