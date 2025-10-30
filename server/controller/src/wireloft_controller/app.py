from __future__ import annotations

from contextlib import contextmanager
from typing import Optional, Iterable, Dict, Any

from backend.db import get_session
from wireloft_config import get_settings


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


# --- Startup scheduling helpers (controller-owned) ---

def _is_interval_like_cron(cron_expr: str) -> bool:
    """Heuristic to detect interval-like cron that should run immediately on startup.

    Consider interval-like when only the minutes field is a step (*/N or X/N),
    and other fields are wildcards ("*" or "?").
    """
    parts = [p.strip() for p in cron_expr.split()]
    if len(parts) != 5:
        return False
    minute, hour, day, month, dow = parts

    def _is_wild(s: str) -> bool:
        return s in ("*", "?")

    def _is_step(s: str) -> bool:
        return "/" in s or s.startswith("*/")

    return _is_step(minute) and _is_wild(hour) and _is_wild(day) and _is_wild(month) and _is_wild(dow)


def _planned_startup_schedules() -> Iterable[Dict[str, Any]]:
    """Yield schedule specs for tasks that should be auto-planned on startup.

    Each spec contains:
      - job_id: stable scheduler job id
      - task_key: task definition key (from registry)
      - resource_type: scheduler resource type str
      - resource_id: int
      - cron: crontab string
    """
    s = get_settings()
    yield {
        "job_id": "auto-new-episode-finder",
        "task_key": "new_episode_finder",
        "resource_type": "show",
        "resource_id": 0,
        "cron": s.new_episode_schedule.find_episodes_cron,
    }


def setup_startup_schedules(scheduler: Optional["AsyncIOScheduler"] = None) -> None:
    """Create or replace controller-owned recurring jobs on startup.

    If scheduler is not provided, it will be obtained via start_scheduler().
    Does nothing if the global scheduler setting is disabled.
    """
    from apscheduler.triggers.cron import CronTrigger
    from wireloft_scheduler.executor import execute_task, trigger_now as scheduler_trigger_now
    from wireloft_scheduler.scheduler import start_scheduler

    if not get_settings().scheduler.enabled:
        return

    sch = scheduler or start_scheduler()

    for spec in _planned_startup_schedules():
        cron_expr = str(spec["cron"]).strip()
        trigger = CronTrigger.from_crontab(cron_expr, timezone=get_settings().timezone)
        sch.add_job(
            execute_task,
            trigger=trigger,
            kwargs=dict(
                def_key=spec["task_key"],
                resource_type=spec["resource_type"],
                resource_id=spec["resource_id"],
                schedule_id=None,
            ),
            id=spec["job_id"],
            replace_existing=True,
        )
        if _is_interval_like_cron(cron_expr):
            # Fire once immediately so users don't wait for the first boundary
            scheduler_trigger_now(
                def_key=spec["task_key"],
                resource_type=spec["resource_type"],
                resource_id=spec["resource_id"],
            )


def app():
    ...