from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from config import get_settings

_scheduler: Optional[AsyncIOScheduler] = None


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
        _scheduler = AsyncIOScheduler(timezone=get_settings().timezone)
        return _scheduler

    job_stores = {"default": SQLAlchemyJobStore(url=get_settings().database_url)}
    loop = _get_or_start_event_loop()
    _scheduler = AsyncIOScheduler(event_loop=loop, jobstores=job_stores)
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


def trigger_now(*, def_key: str, resource_type: str, resource_id: Optional[int] = None, max_retries: Optional[int] = None, **kwargs) -> str:
    from .executor import execute_task

    sch = start_scheduler()

    job = sch.add_job(
        execute_task,
        trigger=DateTrigger(run_date=datetime.now(tz=sch.timezone)),
        kwargs=dict(def_key=def_key, resource_type=resource_type, resource_id=resource_id, schedule_id=None, max_retries=max_retries, **kwargs),
        replace_existing=False,
    )
    return job.id


# --- AsyncIO event loop management for AsyncIOScheduler ---
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None


def _ensure_event_loop_running() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    # If we already have a running loop, reuse it
    if _loop is not None and _loop.is_running():
        return _loop

    # Create and start a dedicated asyncio event loop in a background daemon thread
    loop = asyncio.new_event_loop()
    _loop = loop

    def _run_loop(l: asyncio.AbstractEventLoop):
        asyncio.set_event_loop(l)
        l.run_forever()

    t = threading.Thread(target=_run_loop, args=(loop,), name="wireloft-asyncio-loop", daemon=True)
    _loop_thread = t
    t.start()
    return loop


def _get_or_start_event_loop() -> asyncio.AbstractEventLoop:
    # Use an already running loop in this thread if present, otherwise start our own
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return _ensure_event_loop_running()
