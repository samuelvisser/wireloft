from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from backend.db.core import get_session
from config import get_settings
from task_manager.scheduler.db import TaskOperation, TaskOperationRun, TaskRun
from task_manager.scheduler.operation_control import cancel_operation, cancel_task_run
from task_manager.scheduler.types import OperationStatus, TaskStatus


logger = logging.getLogger(__name__)
WATCHDOG_JOB_ID = "wireloft-stalled-task-watchdog"

# A queued operation may legitimately wait behind a constrained resource queue,
# while WAITING means a running worker is intentionally blocked on an external
# dependency such as Daily Wire request pacing. Neither state is runtime stall
# time, but their TaskRuns still belong to an active operation and must not be
# monitored independently as standalone work.
_WATCHED_OPERATION_STATUSES = {OperationStatus.RUNNING.value}
_OWNED_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
}
_ACTIVE_TASK_STATUSES = {TaskStatus.RUNNING}


@dataclass(frozen=True)
class WatchdogResult:
    operations_canceled: int = 0
    task_runs_canceled: int = 0


@dataclass(frozen=True)
class _ProgressObservation:
    progress: int
    changed_at: datetime


_state_lock = Lock()
_operation_progress: dict[str, _ProgressObservation] = {}
_task_progress: dict[int, _ProgressObservation] = {}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _percent(value: int | None) -> int:
    return max(0, min(100, int(value or 0)))


def _stalled_ids(
        observations: dict,
        current: dict,
        *,
        now: datetime,
        timeout: timedelta,
) -> list:
    stalled: list = []
    current_ids = set(current)

    for resource_id, progress in current.items():
        previous = observations.get(resource_id)
        if previous is None or previous.progress != progress:
            observations[resource_id] = _ProgressObservation(
                progress=progress,
                changed_at=now,
            )
            continue
        if now - previous.changed_at >= timeout:
            stalled.append(resource_id)

    for resource_id in set(observations) - current_ids:
        observations.pop(resource_id, None)

    return stalled


def reset_watchdog_state() -> None:
    """Forget progress observations, giving running work a fresh watchdog window."""
    with _state_lock:
        _operation_progress.clear()
        _task_progress.clear()


def monitor_stalled_work(
        *,
        now: datetime | None = None,
        timeout_minutes: int | None = None,
) -> WatchdogResult:
    """Cancel running tasks/operations whose percentage has stopped changing.

    APScheduler controls when jobs may start and how many may run concurrently,
    but it has no progress-aware runtime timeout. WireLoft samples RUNNING work
    once per minute and remembers when each percentage last changed. Work that is
    merely queued, scheduled, waiting on an external dependency, or waiting for a
    retry is intentionally excluded.

    Runs attached to active TaskOperations are excluded from standalone watchdog
    accounting even when the operation itself is currently WAITING. This preserves
    shared-run semantics without turning an intentional external wait into a stall.
    """
    current_time = _as_utc(now or datetime.now(timezone.utc))
    configured_timeout = (
        int(timeout_minutes)
        if timeout_minutes is not None
        else int(get_settings().scheduler.stalled_task_timeout_minutes)
    )
    timeout = timedelta(minutes=configured_timeout)
    reason = f"Canceled after {configured_timeout} minutes without progress"

    session = get_session()
    try:
        current_operations = {
            operation_id: _percent(progress)
            for operation_id, progress in session.execute(
                select(TaskOperation.id, TaskOperation.progress).where(
                    TaskOperation.status.in_(_WATCHED_OPERATION_STATUSES)
                )
            )
        }
        active_operation_run_ids = set(
            session.scalars(
                select(TaskOperationRun.task_run_id)
                .join(TaskOperation, TaskOperation.id == TaskOperationRun.operation_id)
                .where(TaskOperation.status.in_(_OWNED_OPERATION_STATUSES))
            )
        )
        current_tasks = {
            run_id: _percent(progress)
            for run_id, progress in session.execute(
                select(TaskRun.id, TaskRun.progress).where(
                    TaskRun.status.in_(_ACTIVE_TASK_STATUSES),
                    TaskRun.id.not_in(active_operation_run_ids),
                )
            )
        }
    finally:
        session.close()

    with _state_lock:
        operation_ids = _stalled_ids(
            _operation_progress,
            current_operations,
            now=current_time,
            timeout=timeout,
        )
        task_run_ids = _stalled_ids(
            _task_progress,
            current_tasks,
            now=current_time,
            timeout=timeout,
        )

    operations_canceled = 0
    for operation_id in operation_ids:
        try:
            if cancel_operation(
                operation_id,
                reason=reason,
                acknowledge=False,
            ) is not None:
                operations_canceled += 1
        except ValueError:
            continue

    task_runs_canceled = 0
    for run_id in task_run_ids:
        if cancel_task_run(run_id, reason=reason):
            task_runs_canceled += 1

    if operations_canceled or task_runs_canceled:
        logger.warning(
            "Stalled-work watchdog canceled %s operation(s) and %s task run(s) "
            "after %s minute(s) without progress",
            operations_canceled,
            task_runs_canceled,
            configured_timeout,
        )

    return WatchdogResult(
        operations_canceled=operations_canceled,
        task_runs_canceled=task_runs_canceled,
    )


def install_stalled_work_watchdog() -> None:
    """Install the lightweight scheduler housekeeping job once per process."""
    from task_manager.scheduler.scheduler import WATCHDOG_EXECUTOR_ALIAS, start_scheduler

    reset_watchdog_state()
    scheduler = start_scheduler()
    scheduler.add_job(
        monitor_stalled_work,
        trigger=IntervalTrigger(minutes=1),
        id=WATCHDOG_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=None,
        executor=WATCHDOG_EXECUTOR_ALIAS,
    )
