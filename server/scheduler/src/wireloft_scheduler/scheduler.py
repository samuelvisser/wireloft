from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from wireloft_config import get_settings

_scheduler: Optional[AsyncIOScheduler] = None


def _db_url_for_jobstore() -> str:
    settings = get_settings()

    if settings.database_path:
        return settings.database_path.as_posix()

    # default to app DB (SQLite path in env)
    db_path = get_settings().database_path
    if not db_path:
        # Fallback to a scheduler.db in the data directory if not set
        from wireloft_config.config import PROJECT_ROOT
        db_path = (PROJECT_ROOT / "data" / "wireloft.db").as_posix()
    return f"sqlite:///{db_path}"


def get_trigger(name: str, args: dict):
    if name == "cron":
        return CronTrigger(**args)
    if name == "interval":
        return IntervalTrigger(**args)
    if name == "date":
        # args may include run_date as ISO8601 string or datetime
        run_date = args.get("run_date")
        if isinstance(run_date, str):
            run_date = datetime.fromisoformat(run_date)
        return DateTrigger(run_date=run_date)
    raise ValueError(f"Unknown trigger: {name}")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if not get_settings().scheduler.enabled:
        # create but don't start to simplify call sites (no-ops)
        _scheduler = AsyncIOScheduler()
        return _scheduler

    job_stores = {"default": SQLAlchemyJobStore(url="sqlite:///" + get_settings().database_path.as_posix())}
    _scheduler = AsyncIOScheduler(jobstores=job_stores, timezone=get_settings().timezone)
    _scheduler.start(paused=False)
    return _scheduler


def schedule_job(*, schedule_id: int, def_key: str, resource_type: str, resource_id: int, trigger: str, trigger_args: dict) -> str:
    from .executor import execute_task  # local import to avoid cycles
    sch = start_scheduler()
    job = sch.add_job(
        execute_task,
        trigger=get_trigger(trigger, trigger_args),
        kwargs=dict(def_key=def_key, resource_type=resource_type, resource_id=resource_id, schedule_id=schedule_id),
        replace_existing=True,
        id=f"ts-{schedule_id}",
    )
    return job.id


def remove_job(schedule_id: int) -> None:
    sch = start_scheduler()
    try:
        sch.remove_job(job_id=f"ts-{schedule_id}")
    except Exception:
        pass


def schedule_retry(*, def_key: str, resource_type: str, resource_id: int, run_id: int, run_at: datetime) -> str:
    from .executor import execute_task
    sch = start_scheduler()
    job = sch.add_job(
        execute_task,
        trigger=DateTrigger(run_date=run_at),
        kwargs=dict(def_key=def_key, resource_type=resource_type, resource_id=resource_id, schedule_id=None, run_id=run_id),
        replace_existing=False,
        id=f"retry-{run_id}-{int(run_at.timestamp())}",
    )
    return job.id


def trigger_now(*, def_key: str, resource_type: str, resource_id: int, max_retries: Optional[int] = None) -> str:
    from .executor import execute_task
    sch = start_scheduler()

    job = sch.add_job(
        execute_task,
        trigger=DateTrigger(run_date=datetime.utcnow()),
        kwargs=dict(def_key=def_key, resource_type=resource_type, resource_id=resource_id, schedule_id=None, max_retries=max_retries),
        replace_existing=False,
    )
    return job.id
