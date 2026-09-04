from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from backend.db.core import get_session
from task_manager.scheduler.db import *
from .types import ResourceType, TaskStatus
from .registry import get_task
from .operation_context import operation_context
from .operation_control import (
    RUN_CANCEL_REASON_META_KEY,
    RUN_CANCEL_REQUESTED_META_KEY,
    operation_ids_allow_execution,
    run_cancel_reason,
    run_cancel_requested,
)
from .operations import link_run_to_operations, refresh_operations_for_run
from .results import TaskResult
from config import get_settings
from dailywire_downloader import DownloadCancelled
from task_manager.scheduler import scheduler


class TaskCancellationRequested(Exception):
    """Raised cooperatively when a running TaskRun should stop."""


@dataclass(frozen=True)
class _PreparedExecution:
    run_id: int
    linked_operation_ids: tuple[str, ...]
    call_kwargs: dict[str, Any]


class ProgressUpdater:
    def __init__(self, run_id: int):
        self.run_id = run_id

    def set(self, percent: int, message: Optional[str] = None, meta: Optional[dict] = None):
        p = max(0, min(100, int(percent)))

        # Progress writes deliberately use their own short-lived Session. The
        # executor does not hold a connection while worker code is running, so a
        # fan-out operation cannot exhaust the SQLAlchemy pool merely by filling
        # the APScheduler worker pool.
        s = get_session()
        last_operational_error: OperationalError | None = None
        try:
            for i in range(3):
                try:
                    current_meta = s.execute(
                        select(TaskRun.meta).where(TaskRun.id == self.run_id)
                    ).scalar_one_or_none()
                    if current_meta is None:
                        exists = s.execute(
                            select(TaskRun.id).where(TaskRun.id == self.run_id)
                        ).scalar_one_or_none()
                        if exists is None:
                            raise TaskCancellationRequested("Task resource was deleted")
                    if (
                        isinstance(current_meta, dict)
                        and current_meta.get(RUN_CANCEL_REQUESTED_META_KEY) is True
                    ):
                        reason = current_meta.get(RUN_CANCEL_REASON_META_KEY)
                        raise TaskCancellationRequested(
                            reason if isinstance(reason, str) and reason else "Canceled"
                        )

                    values: dict[str, Any] = {"progress": p}
                    if message is not None:
                        values["message"] = message

                    if meta is not None:
                        merged_meta = dict(current_meta or {})
                        if isinstance(meta, dict):
                            merged_meta.update(meta)
                        else:
                            merged_meta["progress_meta"] = meta
                        values["meta"] = merged_meta

                    result = s.execute(
                        update(TaskRun)
                        .where(TaskRun.id == self.run_id)
                        .values(**values)
                    )
                    if result.rowcount == 0:
                        s.rollback()
                        raise TaskCancellationRequested("Task resource was deleted")
                    s.commit()
                    refresh_operations_for_run(s, self.run_id)
                    s.commit()
                    return
                except OperationalError as exc:
                    last_operational_error = exc
                    s.rollback()
                    time.sleep(0.1 * (2 ** i))

            if last_operational_error is not None:
                raise last_operational_error
        finally:
            s.close()


def _resolve_max_retries(session, def_key: str, schedule_id: Optional[int], override: Optional[int]) -> int:
    if override is not None:
        return override

    # schedule override
    if schedule_id is not None:
        sch = session.get(TaskSchedule, schedule_id)
        if sch and sch.max_retries is not None:
            return int(sch.max_retries)

    # definition default
    td = session.execute(select(TaskDefinition).where(TaskDefinition.key == def_key)).scalar_one()
    if td.default_max_retries is not None:
        return int(td.default_max_retries)

    # global default
    return int(get_settings().scheduler.default_max_retries)


def _backoff_delay(attempt: int) -> float:
    base = float(get_settings().scheduler.retry_backoff_seconds)
    # attempt starts at 1
    return base * (2 ** max(0, attempt - 1))


def _mark_run_canceled(run: TaskRun, message: str = "Canceled") -> None:
    run.status = TaskStatus.CANCELED
    run.message = message
    run.last_error = None
    run.next_retry_at = None


def _prepare_execution(
        *,
        def_key: str,
        resource_type: str,
        resource_id: Optional[int],
        schedule_id: Optional[int],
        run_id: Optional[int],
        max_retries: Optional[int],
        operation_ids: tuple[str, ...],
        operation_slot: str | None,
        worker_callable,
        kwargs: dict[str, Any],
) -> _PreparedExecution | None:
    """Persist the RUNNING attempt, then release its Session before worker code runs."""
    session = get_session()
    try:
        if operation_ids and not operation_ids_allow_execution(session, operation_ids):
            return None

        # A user-created TaskSchedule is owned by its resource relationship. If
        # that resource was deleted, the schedule row is gone and an in-memory
        # APScheduler job from the old row must not manufacture orphan TaskRuns.
        if schedule_id is not None and session.get(TaskSchedule, schedule_id) is None:
            return None

        if run_id is not None:
            run = session.get(TaskRun, run_id)
            if run is None:
                # A deleted resource cascades its TaskRuns. Never recreate a
                # missing retry row with a now-orphaned resource id.
                return None
            if run_cancel_requested(run):
                _mark_run_canceled(run, run_cancel_reason(run))
                run.finished_at = datetime.now(timezone.utc)
                session.commit()
                refresh_operations_for_run(session, run.id)
                session.commit()
                return None

            if kwargs:
                existing_meta = dict(run.meta or {})
                existing_inputs = dict(existing_meta.get("inputs") or {})
                existing_inputs.update(kwargs)
                existing_meta["inputs"] = existing_inputs
                run.meta = existing_meta
        else:
            run = TaskRun(
                schedule_id=schedule_id,
                definition_id=session.execute(
                    select(TaskDefinition.id).where(TaskDefinition.key == def_key)
                ).scalar_one(),
                resource_type=ResourceType(resource_type),
                resource_id=resource_id,
                status=TaskStatus.RUNNING,
                progress=0,
                result=None,
                attempt_count=0,
                started_at=datetime.now(timezone.utc),
                meta={"inputs": dict(kwargs)} if kwargs else None,
            )
            session.add(run)
            session.flush()

        linked_operation_ids = link_run_to_operations(
            session,
            run=run,
            task_key=def_key,
            operation_ids=operation_ids,
            operation_slot=operation_slot,
        )

        run.max_retries = _resolve_max_retries(session, def_key, schedule_id, max_retries)
        run.attempt_count = int(run.attempt_count or 0) + 1
        run.status = TaskStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.finished_at = None
        run.next_retry_at = None
        run.result = None

        stored_inputs = {}
        if isinstance(run.meta, dict):
            stored_inputs = dict(run.meta.get("inputs") or {})
        call_kwargs = {**stored_inputs, **kwargs}
        if (
            "resource_type" in inspect.signature(worker_callable).parameters
            and "resource_type" not in call_kwargs
        ):
            call_kwargs["resource_type"] = resource_type

        prepared_run_id = run.id
        session.commit()
        refresh_operations_for_run(session, prepared_run_id)
        session.commit()
        return _PreparedExecution(
            run_id=prepared_run_id,
            linked_operation_ids=linked_operation_ids,
            call_kwargs=call_kwargs,
        )
    finally:
        session.close()


def _finalize_execution(
        *,
        prepared: _PreparedExecution,
        runtime_ms: int,
        worker_result: Any = None,
        worker_error: Exception | None = None,
        cancellation_reason: str | None = None,
) -> tuple[datetime | None, Exception | None]:
    """Persist terminal/retry state using a fresh short-lived Session.

    Returns ``(retry_at, terminal_error)``. Scheduling occurs only after the
    Session is released so waiting worker jobs never pin database connections.
    """
    session = get_session()
    retry_at: datetime | None = None
    terminal_error: Exception | None = None
    try:
        run = session.get(TaskRun, prepared.run_id)
        if run is None:
            # Resource deletion cascaded the tracking row while the callable was
            # in flight. There is intentionally nothing left to finalize.
            return None, None

        if run_cancel_requested(run):
            cancellation_reason = run_cancel_reason(run, cancellation_reason or "Canceled")

        if cancellation_reason is not None:
            _mark_run_canceled(run, cancellation_reason)
        elif worker_error is None:
            if isinstance(worker_result, TaskResult):
                run.result = worker_result.as_dict()
                run.message = worker_result.summary
            run.status = TaskStatus.SUCCEEDED
            run.progress = 100
            if not run.message:
                run.message = "OK"
            run.last_error = None
            run.next_retry_at = None
        else:
            run.last_error = str(worker_error)
            if run.attempt_count <= run.max_retries:
                delay = _backoff_delay(run.attempt_count)
                retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                run.next_retry_at = retry_at
                run.status = TaskStatus.RETRY_SCHEDULED
                run.message = (
                    f"Retry {run.attempt_count}/{run.max_retries} "
                    f"scheduled in {int(delay)}s"
                )
            else:
                run.status = TaskStatus.FAILED
                run.message = f"Failed after {run.attempt_count} attempts: {run.last_error}"
                terminal_error = worker_error

        run.runtime_ms = runtime_ms
        if run.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED):
            run.finished_at = datetime.now(timezone.utc)
        else:
            run.finished_at = None

        session.commit()
        refresh_operations_for_run(session, run.id)
        session.commit()
        return retry_at, terminal_error
    finally:
        session.close()


def execute_task(
        *,
        def_key: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        schedule_id: Optional[int] = None,
        run_id: Optional[int] = None,
        max_retries: Optional[int] = None,
        operation_ids: tuple[str, ...] | list[str] | None = None,
        operation_slot: str | None = None,
        **kwargs,
):
    """
    Synchronous wrapper executed by APScheduler threadpool.
    Handles retries, progress/result tracking, and generic TaskOperation linkage.

    Database Sessions exist only while preparing/finalizing/checkpointing state;
    worker code never runs while the executor owns a checked-out connection.
    """
    explicit_operation_ids = tuple(
        dict.fromkeys(str(value) for value in (operation_ids or ()) if value)
    )

    _, fn = get_task(def_key)
    prepared = _prepare_execution(
        def_key=def_key,
        resource_type=resource_type,
        resource_id=resource_id,
        schedule_id=schedule_id,
        run_id=run_id,
        max_retries=max_retries,
        operation_ids=explicit_operation_ids,
        operation_slot=operation_slot,
        worker_callable=fn,
        kwargs=dict(kwargs),
    )
    if prepared is None:
        return

    updater = ProgressUpdater(prepared.run_id)
    worker_result: Any = None
    worker_error: Exception | None = None
    cancellation_reason: str | None = None
    started_perf = time.perf_counter()

    try:
        with operation_context(prepared.linked_operation_ids):
            if inspect.iscoroutinefunction(fn):
                worker_result = asyncio.run(
                    fn(resource_id=resource_id, progress=updater, **prepared.call_kwargs)
                )
            else:
                worker_result = fn(  # type: ignore[arg-type]
                    resource_id=resource_id,
                    progress=updater,
                    **prepared.call_kwargs,
                )
    except (TaskCancellationRequested, DownloadCancelled) as exc:
        cancellation_reason = str(exc) or "Canceled"
    except Exception as exc:
        worker_error = exc

    runtime_ms = int((time.perf_counter() - started_perf) * 1000)
    retry_at, terminal_error = _finalize_execution(
        prepared=prepared,
        runtime_ms=runtime_ms,
        worker_result=worker_result,
        worker_error=worker_error,
        cancellation_reason=cancellation_reason,
    )

    if retry_at is not None:
        scheduler.schedule_retry(
            def_key=def_key,
            resource_type=resource_type,
            resource_id=resource_id,
            run_id=prepared.run_id,
            run_at=retry_at,
        )
        return

    if terminal_error is not None:
        raise terminal_error


def trigger_now(
        *,
        def_key: str,
        resource_type: str,
        resource_id: Optional[int],
        max_retries: Optional[int] = None,
        operation_ids: tuple[str, ...] | list[str] | None = None,
        operation_slot: str | None = None,
        **kwargs,
) -> str:
    return scheduler.trigger_now(
        def_key=def_key,
        resource_type=resource_type,
        resource_id=resource_id,
        max_retries=max_retries,
        operation_ids=operation_ids,
        operation_slot=operation_slot,
        **kwargs,
    )
