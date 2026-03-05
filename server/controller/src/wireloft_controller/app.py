from __future__ import annotations

from contextlib import contextmanager
from typing import Optional, Iterable, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.db import get_session
from wireloft_config import get_settings
from wireloft_scheduler.scheduler.helpers import is_interval_like_cron

_controller_initiated = False


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


# --- Startup scheduling helpers (controller-owned) ---
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
        "coalesce": True,
        "cron": s.new_episode_schedule.find_episodes_cron,
    }


def setup_startup_schedules(scheduler: Optional[AsyncIOScheduler] = None) -> None:
    """Create or replace controller-owned recurring jobs on startup.

    If scheduler is not provided, it will be obtained via start_scheduler().
    Does nothing if the global scheduler setting is disabled.
    """
    from apscheduler.triggers.cron import CronTrigger
    from wireloft_scheduler.scheduler.executor import execute_task, trigger_now as scheduler_trigger_now
    from wireloft_scheduler.scheduler.scheduler import start_scheduler

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
            coalesce=spec["coalesce"] if "coalesce" in spec else True,
        )
        if is_interval_like_cron(cron_expr):
            # Fire once immediately so users don't wait for the first boundary
            scheduler_trigger_now(
                def_key=spec["task_key"],
                resource_type=spec["resource_type"],
                resource_id=spec["resource_id"],
            )


def app():
    global _controller_initiated

    if _controller_initiated:
        return

    # Start scheduler and sync task registry if enabled
    try:
        # Ensure controller tasks are imported so they are registered
        from wireloft_scheduler.scheduler.scheduler import start_scheduler
        from wireloft_scheduler.scheduler.registry import sync_registry_to_db
        if get_settings().scheduler.enabled:
            sync_registry_to_db()
            # Start the APScheduler instance
            sch = start_scheduler()

            # Let the controller package plan startup schedules dynamically
            try:
                setup_startup_schedules(scheduler=sch)
            except (ValueError, KeyError, ImportError) as e:
                # Do not crash app if auto-scheduling fails
                pass
    except (AttributeError, RuntimeError, ImportError) as e:
        # Do not crash app if scheduler initialization or registry sync fails
        pass

    _controller_initiated = True