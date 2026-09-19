from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional
from uuid import uuid4

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import BaseScheduler, STATE_PAUSED
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from backend.db.datetime_types import utc_datetime
from config import get_settings
from config.network import is_no_internet_error
from dailywire_downloader import MediaUnavailableError

_scheduler: Optional[AsyncIOScheduler] = None
_critical_scheduler: Optional[AsyncIOScheduler] = None
WATCHDOG_EXECUTOR_ALIAS = "watchdog"
logger = logging.getLogger(__name__)

_scheduled_work_pause_lock = threading.Lock()
_scheduled_work_pauses: dict[str, "ScheduledWorkPause"] = {}
_scheduled_work_pause_owners: dict[str, str] = {}
_resume_scheduled_work_when_clear = False


@dataclass(frozen=True)
class ScheduledWorkPause:
    """A reference-counted lease that keeps normal scheduler work paused."""

    token: str
    reason: str
    owner_key: str | None = None

    def release(self) -> None:
        release_scheduled_work_pause(token=self.token)

    def __enter__(self) -> "ScheduledWorkPause":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


def pause_scheduled_work(
        reason: str,
        *,
        owner_key: str | None = None,
) -> ScheduledWorkPause:
    """Pause normal scheduler dispatch until every pause lease is released.

    Critical tasks use a separate scheduler lane and therefore remain runnable.
    An owner key makes the lease stable across retries of the same durable task.
    """
    global _resume_scheduled_work_when_clear

    scheduler = start_scheduler()
    with _scheduled_work_pause_lock:
        if owner_key is not None:
            existing_token = _scheduled_work_pause_owners.get(owner_key)
            if existing_token is not None:
                existing = _scheduled_work_pauses.get(existing_token)
                if existing is not None:
                    return existing

        if not _scheduled_work_pauses:
            _resume_scheduled_work_when_clear = (
                scheduler.running and scheduler.state != STATE_PAUSED
            )
            if _resume_scheduled_work_when_clear:
                scheduler.pause()

        pause = ScheduledWorkPause(
            token=str(uuid4()),
            reason=reason,
            owner_key=owner_key,
        )
        _scheduled_work_pauses[pause.token] = pause
        if owner_key is not None:
            _scheduled_work_pause_owners[owner_key] = pause.token

    logger.info("Paused scheduled work: %s", reason)
    return pause


def release_scheduled_work_pause(
        *,
        token: str | None = None,
        owner_key: str | None = None,
) -> bool:
    """Release one pause lease and resume only after the final lease is gone."""
    global _resume_scheduled_work_when_clear

    with _scheduled_work_pause_lock:
        if token is None and owner_key is not None:
            token = _scheduled_work_pause_owners.get(owner_key)
        if token is None:
            return False

        pause = _scheduled_work_pauses.pop(token, None)
        if pause is None:
            return False

        if pause.owner_key is not None:
            _scheduled_work_pause_owners.pop(pause.owner_key, None)

        resumed = False
        if not _scheduled_work_pauses:
            should_resume = _resume_scheduled_work_when_clear
            _resume_scheduled_work_when_clear = False
            scheduler = _scheduler
            if (
                should_resume
                and scheduler is not None
                and scheduler.running
                and scheduler.state == STATE_PAUSED
            ):
                # Resume while holding the pause lock so another caller cannot
                # acquire a new lease between the final-release check and resume.
                scheduler.resume()
                resumed = True

    logger.info("Released scheduled-work pause: %s", pause.reason)
    if resumed:
        logger.info("Resumed scheduled work")
    return True


def scheduled_work_is_paused() -> bool:
    with _scheduled_work_pause_lock:
        return bool(_scheduled_work_pauses)


def _reset_scheduled_work_pauses() -> None:
    global _resume_scheduled_work_when_clear

    with _scheduled_work_pause_lock:
        _scheduled_work_pauses.clear()
        _scheduled_work_pause_owners.clear()
        _resume_scheduled_work_when_clear = False


def _execute_task_job(**kwargs) -> None:
    """Run one task without noisy tracebacks for expected external conditions."""
    from .executor import execute_task  # local import to avoid cycles

    try:
        execute_task(**kwargs)
    except Exception as exc:
        if is_no_internet_error(exc):
            # execute_task already persisted and logged the normalized outage.
            return
        if isinstance(exc, MediaUnavailableError):
            # A download worker already tried to refresh an unusable signed media
            # URL before this reaches the scheduler. Keep the persisted task
            # failure visible without asking APScheduler to dump the whole causal
            # traceback for an expected authentication/media-availability state.
            logger.warning(
                "Task %s could not access Daily Wire media: %s",
                kwargs.get("def_key", "unknown"),
                exc,
            )
            return
        raise


def get_trigger(name: str, args: dict):
    trigger_args = dict(args)
    # Legacy: remove timezone from trigger, we use the WireLoft TZ timezone
    trigger_args.pop("timezone", None)
    app_timezone = get_settings().timezone

    if name == "cron":
        return CronTrigger(timezone=app_timezone, **trigger_args)
    if name == "interval":
        return IntervalTrigger(timezone=app_timezone, **trigger_args)
    if name == "date":
        run_date = trigger_args.pop("run_date", None)
        if isinstance(run_date, str):
            run_date = datetime.fromisoformat(run_date)
        return DateTrigger(run_date=run_date, timezone=app_timezone)
    raise ValueError(f"Unknown trigger: {name}")


def _new_scheduler(loop: asyncio.AbstractEventLoop | None = None) -> AsyncIOScheduler:
    settings = get_settings()
    kwargs = {
        "timezone": settings.timezone,
        "executors": {
            "default": ThreadPoolExecutor(max_workers=settings.scheduler.max_workers),
            # The stalled-work watchdog must remain runnable when every normal
            # worker slot is occupied by the work it is responsible for watching.
            WATCHDOG_EXECUTOR_ALIAS: ThreadPoolExecutor(max_workers=1),
        },
    }
    if loop is not None:
        kwargs["event_loop"] = loop
    return AsyncIOScheduler(**kwargs)


def _new_critical_scheduler(
        loop: asyncio.AbstractEventLoop | None = None,
) -> AsyncIOScheduler:
    settings = get_settings()
    kwargs = {
        "timezone": settings.timezone,
        # Critical work is intentionally serialized. Its defining property is
        # that normal scheduled work must remain paused while it is incomplete.
        "executors": {
            "default": ThreadPoolExecutor(max_workers=1),
        },
    }
    if loop is not None:
        kwargs["event_loop"] = loop
    return AsyncIOScheduler(**kwargs)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler, _critical_scheduler
    if _scheduler is not None and _critical_scheduler is not None:
        return _scheduler

    # Task execution is core infrastructure and remains available even when
    # automatic scheduling is disabled. scheduler.enabled is enforced where
    # recurring/event-driven automation is installed, not here.
    #
    # Normal work and critical work share an event loop but use separate
    # schedulers. This lets critical maintenance continue while normal dispatch
    # is paused without special-casing the worker implementation.
    loop = _get_or_start_event_loop()
    if _scheduler is None:
        _scheduler = _new_scheduler(loop)
        _scheduler.start(paused=False)
    if _critical_scheduler is None:
        _critical_scheduler = _new_critical_scheduler(loop)
        _critical_scheduler.start(paused=False)
    return _scheduler


def _shutdown_one_scheduler(
        scheduler: AsyncIOScheduler | None,
        *,
        wait: bool,
        current_loop: asyncio.AbstractEventLoop | None,
) -> None:
    if scheduler is None or not scheduler.running:
        return

    scheduler_loop = scheduler._eventloop
    if scheduler_loop is not None and scheduler_loop is current_loop:
        # AsyncIOScheduler.shutdown() normally queues this work onto its loop.
        # During ASGI lifespan shutdown we are already on that loop and need
        # teardown to finish before the loop itself is allowed to close.
        BaseScheduler.shutdown(scheduler, wait=wait)
        scheduler._stop_timer()
        scheduler._eventloop = None
    else:
        scheduler.shutdown(wait=wait)


def shutdown_scheduler(wait: bool = True) -> None:
    """Shut down normal and critical scheduler lanes and reset lifecycle state."""
    global _scheduler, _critical_scheduler, _loop, _loop_thread

    normal_scheduler = _scheduler
    critical_scheduler = _critical_scheduler
    _scheduler = None
    _critical_scheduler = None
    _reset_scheduled_work_pauses()

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    _shutdown_one_scheduler(
        normal_scheduler,
        wait=wait,
        current_loop=current_loop,
    )
    _shutdown_one_scheduler(
        critical_scheduler,
        wait=wait,
        current_loop=current_loop,
    )

    # When the schedulers own our fallback thread, queue a barrier behind both
    # shutdown callbacks before stopping that loop.
    if _loop is not None and _loop.is_running() and _loop is not current_loop:
        shutdown_complete = threading.Event()
        _loop.call_soon_threadsafe(shutdown_complete.set)
        shutdown_complete.wait(timeout=5)

    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
    if _loop_thread is not None and _loop_thread.is_alive():
        _loop_thread.join(timeout=5)

    _loop = None
    _loop_thread = None


def _task_meta(def_key: str):
    from .registry import get_task

    try:
        meta, _ = get_task(def_key)
    except KeyError:
        return None
    return meta


def _task_pauses_scheduled_work(def_key: str) -> bool:
    meta = _task_meta(def_key)
    return bool(meta is not None and meta.pauses_scheduled_work)


def _release_job_scheduled_work_pause(job_kwargs: dict) -> None:
    pause_token = job_kwargs.get("_scheduled_work_pause_token")
    if isinstance(pause_token, str):
        release_scheduled_work_pause(token=pause_token)


def _scheduler_for_task(def_key: str) -> AsyncIOScheduler:
    normal_scheduler = start_scheduler()
    if not _task_pauses_scheduled_work(def_key):
        return normal_scheduler
    if _critical_scheduler is None:
        raise RuntimeError("Critical scheduler was not initialized")
    return _critical_scheduler


def _started_task_schedulers() -> tuple[AsyncIOScheduler, ...]:
    schedulers = [
        scheduler
        for scheduler in (_scheduler, _critical_scheduler)
        if scheduler is not None
    ]
    return tuple(dict.fromkeys(schedulers))


def schedule_job(*, schedule_id: int, def_key: str, resource_type: str, resource_id: int, trigger: str, trigger_args: dict) -> str:
    sch = start_scheduler()
    job = sch.add_job(
        _execute_task_job,
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

    # Deleting a database resource must not start scheduler infrastructure as a side effect.
    schedulers = _started_task_schedulers()
    if not schedulers:
        return 0

    removed = 0
    for sch in schedulers:
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
                _release_job_scheduled_work_pause(job_kwargs)
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

    start_scheduler()
    removed = 0
    for sch in _started_task_schedulers():
        for job in list(sch.get_jobs()):
            run_id = dict(job.kwargs or {}).get("run_id")
            if run_id not in run_id_set:
                continue
            try:
                sch.remove_job(job.id)
                _release_job_scheduled_work_pause(dict(job.kwargs or {}))
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
    """Remove queued operation dispatches and retries from all scheduler lanes.

    A job explicitly owned by more than one operation is left in place; the
    executor will decide whether any of those operations still needs it. Retry
    jobs are removed only for TaskRuns that are not shared with another active
    operation.

    APScheduler cannot terminate a Python callable that is already executing in a
    worker thread. Running work is therefore canceled cooperatively by the task
    executor; this helper prevents exclusively owned work that has not started yet
    from doing so.
    """
    start_scheduler()
    run_id_set = {int(value) for value in run_ids}
    removed = 0
    for sch in _started_task_schedulers():
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
                _release_job_scheduled_work_pause(job_kwargs)
                removed += 1
            except Exception:
                # The date job may have started between get_jobs() and remove_job().
                pass
    return removed


def schedule_retry(*, def_key: str, resource_type: str, resource_id: int, run_id: int, run_at: datetime) -> str:
    sch = _scheduler_for_task(def_key)
    run_at = utc_datetime(run_at)
    job = sch.add_job(
        _execute_task_job,
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
    from .operation_context import current_operation_ids

    sch = _scheduler_for_task(def_key)
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

    dispatch_pause = None
    meta = _task_meta(def_key)
    if meta is not None and meta.pauses_scheduled_work:
        # Acquire before the critical job is submitted. The executor transfers
        # this temporary lease to the durable TaskRun once execution begins.
        dispatch_pause = pause_scheduled_work(meta.title)
        execution_kwargs["_scheduled_work_pause_token"] = dispatch_pause.token

    try:
        job = sch.add_job(
            _execute_task_job,
            trigger=DateTrigger(run_date=datetime.now(tz=sch.timezone)),
            kwargs=execution_kwargs,
            replace_existing=False,
            # Operation fan-out can legitimately queue hundreds of immediate jobs.
            # They should wait for a worker rather than expire while the pool is busy.
            misfire_grace_time=None,
        )
    except Exception:
        if dispatch_pause is not None:
            dispatch_pause.release()
        raise
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
