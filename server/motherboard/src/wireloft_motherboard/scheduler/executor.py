from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from backend.db.core import get_session
from wireloft_scheduler.scheduler.db import *
from .types import ResourceType, TaskStatus
from .registry import get_task
from wireloft_config import get_settings
from wireloft_scheduler import scheduler


class ProgressUpdater:
    def __init__(self, run: TaskRun):
        self.run = run

    def set(self, percent: int, message: Optional[str] = None, meta: Optional[dict] = None):
        p = max(0, min(100, int(percent)))
        values = {"progress": p}
        if message is not None:
            values["message"] = message

        # Use a throwaway Session so failures can't poison the main one
        s = get_session()
        try:
            for i in range(3):
                try:
                    # Merge meta with existing to avoid overwriting stored inputs
                    if meta is not None:
                        existing_meta = s.execute(
                            select(TaskRun.meta).where(TaskRun.id == self.run.id)
                        ).scalar_one_or_none()
                        merged_meta = dict(existing_meta or {})
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


def execute_task(
        *,
        def_key: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        schedule_id: Optional[int] = None,
        run_id: Optional[int] = None,
        max_retries: Optional[int] = None,
        **kwargs,
):
    """
    Synchronous wrapper executed by APScheduler threadpool.
    Handles retries and progress tracking.
    """
    session = get_session()

    try:
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
                    started_at=datetime.now(timezone.utc),
                )
                session.add(run)
                session.flush()
            else:
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
                attempt_count=0,
                started_at=datetime.now(timezone.utc),
                meta={"inputs": dict(kwargs)} if kwargs else None,
            )
            session.add(run)
            session.flush()

        # Determine max retries policy once and store on run
        mr = _resolve_max_retries(session, def_key, schedule_id, max_retries or meta.default_max_retries)
        run.max_retries = mr
        # Increase attempt and start timing
        run.attempt_count = int(run.attempt_count or 0) + 1
        run.status = TaskStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
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
        try:
            if inspect.iscoroutinefunction(fn):
                # run async function in dedicated loop
                asyncio.run(fn(resource_id=resource_id, progress=updater, **call_kwargs))
            else:
                fn(resource_id=resource_id, progress=updater, **call_kwargs)  # type: ignore[arg-type]
            # success
            run.status = TaskStatus.SUCCEEDED
            run.progress = 100
            run.message = "OK"
        except Exception as e:
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
                # enqueue retry using run_id
                scheduler.schedule_retry(def_key=def_key, resource_type=resource_type, resource_id=resource_id, run_id=run.id, run_at=when)
                return
            else:
                run.status = TaskStatus.FAILED
                run.message = f"Failed after {run.attempt_count} attempts: {run.last_error}"
                raise
        finally:
            run.finished_at = datetime.now(timezone.utc)
            run.runtime_ms = int((time.perf_counter() - started_perf) * 1000)
            session.commit()
    finally:
        session.close()


def trigger_now(*, def_key: str, resource_type: str, resource_id: Optional[int], max_retries: Optional[int] = None, **kwargs) -> str:
    return scheduler.trigger_now(def_key=def_key, resource_type=resource_type, resource_id=resource_id, max_retries=max_retries, **kwargs)