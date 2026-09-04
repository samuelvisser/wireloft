from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Iterable, Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import BaseScheduler
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


def _new_scheduler(loop: asyncio.AbstractEventLoop | None = None) -> AsyncIOScheduler:
    settings = get_settings()
    kwargs = {
        "timezone": settings.timezone,
        "executors": {
            "default": ThreadPoolExecutor(max_workers=settings.scheduler.max_workers),
        },
    }
    if loop is not None:
        kwargs["event_loop"] = loop
    return AsyncIOScheduler(**kwargs)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if not get_settings().scheduler.enabled:
        # create but don't start to simplify call sites (no-ops)
        _scheduler = _new_scheduler()
        return _scheduler

    # Use in-memory job store (default MemoryJobStore). User-created schedules
    # are reloaded from TaskSchedule on startup. Honor WireLoft's configured
    # worker limit instead of APScheduler's independent default of ten threads.
    loop = _get_or_start_event_loop()
    _scheduler = _new_scheduler(loop)
    _scheduler.start(paused=False)
    return _scheduler


def shutdown_scheduler(wait: bool = True) -> None:
    """Shut down and reset scheduler state for a clean application lifecycle."""
    global _scheduler, _loop, _loop_thread

    scheduler = _scheduler
    scheduler_loop = scheduler._eventloop if scheduler is not None else None
    _scheduler = None

    if scheduler is not None and scheduler.running:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if scheduler_loop is not None and scheduler_loop is current_loop:
            # AsyncIOScheduler.shutdown() normally queues this work onto its loop.
            # During ASGI lifespan shutdown we are already on that loop and need
            # teardown to finish before the loop itself is allowed to close.
            BaseScheduler.shutdown(scheduler, wait=wait)
            scheduler._stop_timer()
            scheduler._eventloop = None
        else:
            scheduler.shutdown(wait=wait)

        # When the scheduler owns our fallback thread, queue a barrier behind
        # its shutdown callback before stopping that loop.
        if scheduler_loop is not None and scheduler_loop is _loop and scheduler_loop.is_running():
            shutdown_complete = threading.Event()
            scheduler_loop.call_soon_threadsafe(shutdown_complete.set)
            shutdown_complete.wait(timeout=5)

    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
    if _loop_thread is not None and _loop_thread.is_alive():
        _loop_thread.join(timeout=5)

    _loop = None
    _loop_thread = None


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


def cancel_pending_resource_jobs(resources: Iterable[tuple[str, int]]) -> int:
    """Remove queued/recurring APScheduler jobs whose domain resource was deleted."""
    resource_keys = {(str(resource_type), int(resource_id)) for resource_type, resource_id in resources}
    if not resource_keys:
        return 0

    # Deleting a database resource must not start the scheduler as a side effect.
    sch = _scheduler
    if sch is None:
        return 0

    removed = 0
    for job in list(sch.get_jobs()):
        job_kwargs = dict(job.kwargs or {})
        raw_resource_type = job_kwargs.get("resource_type")
        resource_type = (
            raw_resource_type.value
            if hasattr(raw_resource_type, "value")
            else raw_resource_type
        )
        resource_id = job_kwargs.get("resource_id")
        try:
            key = (str(resource_type), int(resource_id))
        except (TypeError, ValueError):
            continue
        if key not in resource_keys:
            continue
        try:
            sch.remove_job(job.id)
            removed += 1
        except Exception:
            # The job may have started between get_jobs() and remove_job().
            pass
    return removed


def cancel_pending_task_run_jobs(run_ids: Iterable[int]) -> int:
    """Remove in-memory retry/dispatch jobs belonging to TaskRuns."""
    run_id_set = {int(value) for value in run_ids}
    if not run_id_set:
        return 0

    sch = start_scheduler()
    removed = 0
    for job in list(sch.get_jobs()):
        run_id = dict(job.kwargs or {}).get("run_id")
        if run_id not in run_id_set:
            continue
        try:
            sch.remove_job(job.id)
            removed += 1
        except Exception:
            # The date job may have started between get_jobs() and remove_job().
            pass
    return removed


def cancel_pending_operation_jobs(
        *,
        operation_id: str,
        run_ids: Iterable[int] = (),
) -> int:
    """Remove queued operation dispatches and retries from the in-memory scheduler.

    A job explicitly owned by more than one operation is left in place; the
    executor will decide whether any of those operations still needs it. Retry
    jobs are removed only for TaskRuns that are not shared with another active
    operation.

    APScheduler cannot terminate a Python callable that is already executing in a
    worker thread. Running work is therefore canceled cooperatively by the task
    executor; this helper prevents exclusively owned work that has not started yet
    from doing so.
    """
    sch = start_scheduler()
    run_id_set = {int(value) for value in run_ids}
    removed = 0
    for job in list(sch.get_jobs()):
        job_kwargs = dict(job.kwargs or {})
        operation_ids = tuple(str(value) for value in (job_kwargs.get("operation_ids") or ()))
        run_id = job_kwargs.get("run_id")
        exclusively_owned = operation_ids == (operation_id,)
        owned_retry = run_id in run_id_set
        if not exclusively_owned and not owned_retry:
            continue
        try:
            sch.remove_job(job.id)
            removed += 1
        except Exception:
            # The date job may have started between get_jobs() and remove_job().
            pass
    return removed


def schedule_retry(*, def_key: str, resource_type: str, resource_id: int, run_id: int, run_at: datetime) -> str:
    from .executor import execute_task
    sch = start_scheduler()
    job = sch.add_job(
        execute_task,
        trigger=DateTrigger(run_date=run_at),
        kwargs=dict(def_key=def_key, resource_type=resource_type, resource_id=resource_id, schedule_id=None, run_id=run_id),
        replace_existing=False,
        id=f"retry-{run_id}-{int(run_at.timestamp())}",
        # Retries are durable in TaskRun. A saturated worker pool must delay them,
        # not make APScheduler discard them as a misfire.
        misfire_grace_time=None,
    )
    return job.id


def trigger_now(
        *,
        def_key: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        max_retries: Optional[int] = None,
        operation_ids: Iterable[str] | None = None,
        operation_slot: str | None = None,
        **kwargs,
) -> str:
    """Trigger a task immediately, inheriting the current operation context.

    Operation correlation is scheduler infrastructure, not a worker parameter.
    Child tasks started from inside a worker automatically remain associated with
    the same high-level operation unless the caller explicitly overrides it.
    """
    from .executor import execute_task
    from .operation_context import current_operation_ids

    sch = start_scheduler()
    inherited_ids = tuple(operation_ids) if operation_ids is not None else current_operation_ids()
    execution_kwargs = dict(
        def_key=def_key,
        resource_type=resource_type,
        resource_id=resource_id,
        schedule_id=None,
        max_retries=max_retries,
        **kwargs,
    )
    if inherited_ids:
        execution_kwargs["operation_ids"] = inherited_ids
    if operation_slot is not None:
        execution_kwargs["operation_slot"] = operation_slot

    job = sch.add_job(
        execute_task,
        trigger=DateTrigger(run_date=datetime.now(tz=sch.timezone)),
        kwargs=execution_kwargs,
        replace_existing=False,
        # Operation fan-out can legitimately queue hundreds of immediate jobs.
        # They should wait for a worker rather than expire while the pool is busy.
        misfire_grace_time=None,
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
