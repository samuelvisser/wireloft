from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from backend.db.core import get_session
from task_manager.scheduler.db import *
from .types import ResourceType, TaskStatus
from .registry import get_task
from .operation_context import operation_context
from .operation_control import (
    RUN_CANCEL_REQUESTED_META_KEY,
    operation_ids_allow_execution,
    run_cancel_requested,
)
from .operations import link_run_to_operations, refresh_operations_for_run
from .results import TaskResult
from config import get_settings
from dailywire_downloader import DownloadCancelled
from task_manager.scheduler import scheduler


class TaskCancellationRequested(Exception):
    """Raised cooperatively when the UI asks a running TaskRun to stop."""


class ProgressUpdater:
    def __init__(self, run: TaskRun):
        self.run = run

    def set(self, percent: int, message: Optional[str] = None, meta: Optional[dict] = None):
        p = max(0, min(100, int(percent)))

        # Use a throwaway Session so failures can't poison the main one. Reading
        # the latest metadata here also makes progress checkpoints cooperative
        # cancellation points for long-running worker services.
        s = get_session()
        try:
            for i in range(3):
                try:
                    current_meta = s.execute(
                        select(TaskRun.meta).where(TaskRun.id == self.run.id)
                    ).scalar_one_or_none()
                    if (
                        isinstance(current_meta, dict)
                        and current_meta.get(RUN_CANCEL_REQUESTED_META_KEY) is True
                    ):
                        raise TaskCancellationRequested("Canceled by user")

                    values = {"progress": p}
                    if message is not None:
                        values["message"] = message

                    # Merge caller-provided metadata with the existing run metadata
                    # without introducing scheduler-only progress markers. Active
                    # TaskRun progress above zero is itself sufficient to tell a
                    # TaskOperation that the worker is reporting granular progress.
                    if meta is not None:
                        merged_meta = dict(current_meta or {})
                        if isinstance(meta, dict):
                            merged_meta.update(meta)
                        else:
                            merged_meta["progress_meta"] = meta
                        values["meta"] = merged_meta

                    s.execute(
                        update(TaskRun)
                        .where(TaskRun.id == self.run.id)
                        .values(**values)
                    )
                    s.commit()
                    refresh_operations_for_run(s, self.run.id)
                    s.commit()
                    return
                except OperationalError:
                    s.rollback()
                    time.sleep(0.1 * (2 ** i))
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


def _refresh_run_cancellation(session, run: TaskRun) -> bool:
    session.refresh(run, attribute_names=["meta"])
    return run_cancel_requested(run)


def _mark_run_canceled(run: TaskRun, message: str = "Canceled by user") -> None:
    run.status = TaskStatus.CANCELED
    run.message = message
    run.last_error = None
    run.next_retry_at = None


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
    """
    session = get_session()

    try:
        explicit_operation_ids = tuple(
            dict.fromkeys(str(value) for value in (operation_ids or ()) if value)
        )
        if explicit_operation_ids and not operation_ids_allow_execution(session, explicit_operation_ids):
            return

        # Load callable
        meta, fn = get_task(def_key)

        # Prepare or load TaskRun
        if run_id is not None:
            run = session.get(TaskRun, run_id)
            if run is None:
                # if missing (deleted?), create anew
                run = TaskRun(
                    schedule_id=schedule_id,
                    definition_id=session.execute(select(TaskDefinition.id).where(TaskDefinition.key == def_key)).scalar_one(),
                    resource_type=ResourceType(resource_type),
                    resource_id=resource_id,
                    status=TaskStatus.RUNNING,
                    progress=0,
                    meta={"inputs": dict(kwargs)} if kwargs else None,
                    result=None,
                    started_at=datetime.now(timezone.utc),
                )
                session.add(run)
                session.flush()
            else:
                if run_cancel_requested(run):
                    _mark_run_canceled(run)
                    run.finished_at = datetime.now(timezone.utc)
                    session.commit()
                    refresh_operations_for_run(session, run.id)
                    session.commit()
                    return

                # Merge any provided kwargs into existing inputs (do not drop previous ones)
                if kwargs:
                    existing_meta = dict(run.meta or {})
                    existing_inputs = dict(existing_meta.get("inputs") or {})
                    existing_inputs.update(dict(kwargs))
                    existing_meta["inputs"] = existing_inputs
                    run.meta = existing_meta
        else:
            run = TaskRun(
                schedule_id=schedule_id,
                definition_id=session.execute(select(TaskDefinition.id).where(TaskDefinition.key == def_key)).scalar_one(),
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
            operation_ids=explicit_operation_ids,
            operation_slot=operation_slot,
        )

        # Determine max retries policy once and store on run. An explicit zero
        # means "do not retry" and must not fall through to task defaults.
        mr = _resolve_max_retries(session, def_key, schedule_id, max_retries)
        run.max_retries = mr
        # Increase attempt and start timing
        run.attempt_count = int(run.attempt_count or 0) + 1
        run.status = TaskStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.finished_at = None
        run.next_retry_at = None
        run.result = None
        session.commit()
        refresh_operations_for_run(session, run.id)
        session.commit()

        # Execute task callable (supports sync or async)
        updater = ProgressUpdater(run)
        started_perf = time.perf_counter()
        # Determine final kwargs passed to the task:
        # start from stored inputs (for retries), then overlay with explicitly provided kwargs
        stored_inputs = {}
        if isinstance(run.meta, dict):
            stored_inputs = dict(run.meta.get("inputs") or {})
        call_kwargs = {**stored_inputs, **kwargs}

        # Some tasks are triggered from more than one resource type (e.g. a cron
        # sweep vs. a single-episode event) and need to know which one this run
        # is for. Forward it only when the task actually declares the parameter,
        # and only as a call-time value: it must never be persisted into
        # run.meta as if it were a genuine input, so retries keep recomputing it
        # from the resource_type this execute_task call was given.
        if "resource_type" in inspect.signature(fn).parameters and "resource_type" not in call_kwargs:
            call_kwargs["resource_type"] = resource_type
        try:
            with operation_context(linked_operation_ids):
                if inspect.iscoroutinefunction(fn):
                    # run async function in dedicated loop
                    worker_result = asyncio.run(fn(resource_id=resource_id, progress=updater, **call_kwargs))
                else:
                    worker_result = fn(resource_id=resource_id, progress=updater, **call_kwargs)  # type: ignore[arg-type]

            if _refresh_run_cancellation(session, run):
                raise TaskCancellationRequested("Canceled by user")

            if isinstance(worker_result, TaskResult):
                run.result = worker_result.as_dict()
                run.message = worker_result.summary
            # success
            run.status = TaskStatus.SUCCEEDED
            run.progress = 100
            if not run.message:
                run.message = "OK"
            run.last_error = None
            run.next_retry_at = None
        except (TaskCancellationRequested, DownloadCancelled) as e:
            _mark_run_canceled(run, str(e) or "Canceled by user")
        except Exception as e:
            if _refresh_run_cancellation(session, run):
                _mark_run_canceled(run)
            else:
                # failure
                run.last_error = str(e)
                # Decide retry
                if run.attempt_count <= run.max_retries:
                    delay = _backoff_delay(run.attempt_count)
                    when = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    run.next_retry_at = when
                    run.status = TaskStatus.RETRY_SCHEDULED
                    run.message = f"Retry {run.attempt_count}/{run.max_retries} scheduled in {int(delay)}s"
                    session.commit()  # commit before scheduling retry
                    refresh_operations_for_run(session, run.id)
                    session.commit()
                    # enqueue retry using run_id; operation linkage lives on the run
                    scheduler.schedule_retry(def_key=def_key, resource_type=resource_type, resource_id=resource_id, run_id=run.id, run_at=when)
                    return
                else:
                    run.status = TaskStatus.FAILED
                    run.message = f"Failed after {run.attempt_count} attempts: {run.last_error}"
                    raise
        finally:
            run.runtime_ms = int((time.perf_counter() - started_perf) * 1000)
            if run.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED):
                run.finished_at = datetime.now(timezone.utc)
            else:
                run.finished_at = None
            session.commit()
            refresh_operations_for_run(session, run.id)
            session.commit()
    finally:
        session.close()


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
