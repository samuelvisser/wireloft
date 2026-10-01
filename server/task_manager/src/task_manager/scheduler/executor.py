from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from backend.db.core import begin_write_transaction, get_session
from task_manager.scheduler.db import *
from task_manager.scheduler.db.TaskRun import (
    TASK_RUN_COMPLETION_PROGRESS_META_KEY,
    TASK_RUN_PROGRESS_META_KEY,
    TASK_RUN_WAIT_STATE_META_KEY,
)
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
from .operations import (
    link_run_to_operations,
    refresh_operations_for_run,
)
from .results import TaskResult
from config import get_settings
from config.network import (
    NO_INTERNET_CONNECTION_MESSAGE,
    NoInternetConnectionError,
    is_no_internet_error,
)
from dailywire_api.pacing import RequestCancelled, RequestWait, request_context
from dailywire_downloader import DownloadCancelled
from task_manager.scheduler import scheduler


logger = logging.getLogger(__name__)
_WAIT_UNCHANGED = object()
_DAILY_WIRE_COOLDOWN_REASON = "daily_wire_request_cooldown"
_DAILY_WIRE_COOLDOWN_MESSAGE = "Waiting for Daily Wire request cooldown. Will resume soon."


class TaskCancellationRequested(Exception):
    """Raised cooperatively when a running TaskRun should stop."""


@dataclass(frozen=True)
class _PreparedExecution:
    run_id: int
    linked_operation_ids: tuple[str, ...]
    call_kwargs: dict[str, Any]


def _run_has_active_operation_owner(session, run_id: int) -> bool:
    operation_ids = tuple(
        session.scalars(
            select(TaskOperationRun.operation_id).where(
                TaskOperationRun.task_run_id == run_id
            )
        )
    )
    return not operation_ids or operation_ids_allow_execution(session, operation_ids)


class ProgressUpdater:
    """Generic progress and cooperative-cancellation channel for a TaskRun.

    Workers report percentage, message and structured live metadata through
    ``set``. Percentage values are deliberately discarded when the registered
    task has ``tracks_progress=False``, while messages, metadata, waits and
    cancellation remain available. Long-running libraries may also use the
    updater itself as a ``should_cancel`` callback; cancellation is then driven
    by the same durable TaskRun state used for every other worker rather than by
    worker-specific generation flags.
    """

    _CANCEL_CHECK_INTERVAL_SECONDS = 0.25

    def __init__(self, run_id: int, *, tracks_progress: bool = True):
        self.run_id = run_id
        self.tracks_progress = tracks_progress
        self._last_cancel_check = 0.0
        self._cancelled = False
        self._cancel_reason = "Canceled"

    def _read_cancellation(self, *, force: bool = False) -> tuple[bool, str]:
        if self._cancelled:
            return True, self._cancel_reason

        now = time.monotonic()
        if not force and now - self._last_cancel_check < self._CANCEL_CHECK_INTERVAL_SECONDS:
            return False, self._cancel_reason
        self._last_cancel_check = now

        s = get_session()
        try:
            row = s.execute(
                select(TaskRun.status, TaskRun.meta).where(TaskRun.id == self.run_id)
            ).one_or_none()
            if row is None:
                self._cancelled = True
                self._cancel_reason = "Task resource was deleted"
                return True, self._cancel_reason

            status, meta = row
            requested = (
                isinstance(meta, dict)
                and meta.get(RUN_CANCEL_REQUESTED_META_KEY) is True
            )
            if status == TaskStatus.CANCELED or requested:
                reason = (
                    meta.get(RUN_CANCEL_REASON_META_KEY)
                    if isinstance(meta, dict)
                    else None
                )
                self._cancelled = True
                self._cancel_reason = (
                    reason if isinstance(reason, str) and reason else "Canceled"
                )
                return True, self._cancel_reason
            if not _run_has_active_operation_owner(s, self.run_id):
                self._cancelled = True
                self._cancel_reason = "Owning operation was canceled"
                return True, self._cancel_reason
            return False, self._cancel_reason
        except Exception:
            # Cancellation checks are deliberately conservative: transient DB
            # contention must not abort irreversible worker/file work. The normal
            # progress/finalization checkpoints will try again shortly.
            s.rollback()
            return False, self._cancel_reason
        finally:
            s.close()

    def __call__(self) -> bool:
        """Return True when the worker should stop, suitable for downloader callbacks."""
        canceled, _ = self._read_cancellation()
        return canceled

    def raise_if_cancelled(self) -> None:
        canceled, reason = self._read_cancellation(force=True)
        if canceled:
            raise TaskCancellationRequested(reason)

    def set(
            self,
            percent: int,
            message: Optional[str] = None,
            meta: Optional[dict[str, Any]] = None,
            *, completion_percent: int | None = None,
            wait_state: dict[str, Any] | None | object = _WAIT_UNCHANGED,
    ) -> None:
        p = max(0, min(100, int(percent)))
        completion = (
            None
            if completion_percent is None
            else max(0, min(100, int(completion_percent)))
        )

        # Progress writes deliberately use their own short-lived Session. The
        # executor does not hold a connection while worker code is running, so a
        # fan-out operation cannot exhaust the SQLAlchemy pool merely by filling
        # the APScheduler worker pool.
        s = get_session()
        last_operational_error: OperationalError | None = None
        try:
            for i in range(3):
                try:
                    begin_write_transaction(s)
                    row = s.execute(
                        select(TaskRun.status, TaskRun.meta).where(TaskRun.id == self.run_id)
                    ).one_or_none()
                    if row is None:
                        self._cancelled = True
                        self._cancel_reason = "Task resource was deleted"
                        raise TaskCancellationRequested(self._cancel_reason)

                    status, current_meta = row
                    if (
                        status == TaskStatus.CANCELED
                        or (
                            isinstance(current_meta, dict)
                            and current_meta.get(RUN_CANCEL_REQUESTED_META_KEY) is True
                        )
                    ):
                        reason = (
                            current_meta.get(RUN_CANCEL_REASON_META_KEY)
                            if isinstance(current_meta, dict)
                            else None
                        )
                        self._cancelled = True
                        self._cancel_reason = (
                            reason if isinstance(reason, str) and reason else "Canceled"
                        )
                        raise TaskCancellationRequested(self._cancel_reason)
                    if not _run_has_active_operation_owner(s, self.run_id):
                        self._cancelled = True
                        self._cancel_reason = "Owning operation was canceled"
                        raise TaskCancellationRequested(self._cancel_reason)

                    values: dict[str, Any] = {
                        "progress": p if self.tracks_progress else None,
                    }
                    if message is not None:
                        values["message"] = message

                    if (
                        meta is not None
                        or (self.tracks_progress and completion is not None)
                        or wait_state is not _WAIT_UNCHANGED
                    ):
                        merged_meta = dict(current_meta or {})
                        if meta is not None:
                            current_progress_meta = merged_meta.get(TASK_RUN_PROGRESS_META_KEY)
                            merged_progress_meta = (
                                dict(current_progress_meta)
                                if isinstance(current_progress_meta, dict)
                                else {}
                            )
                            merged_progress_meta.update(meta)
                            merged_meta[TASK_RUN_PROGRESS_META_KEY] = merged_progress_meta
                        if self.tracks_progress and completion is not None:
                            merged_meta[TASK_RUN_COMPLETION_PROGRESS_META_KEY] = completion
                        if wait_state is not _WAIT_UNCHANGED:
                            if wait_state is None:
                                merged_meta.pop(TASK_RUN_WAIT_STATE_META_KEY, None)
                            else:
                                merged_meta[TASK_RUN_WAIT_STATE_META_KEY] = wait_state
                        values["meta"] = merged_meta

                    result = s.execute(
                        update(TaskRun)
                        .where(
                            TaskRun.id == self.run_id,
                            TaskRun.status == TaskStatus.RUNNING,
                            func.coalesce(TaskRun.meta[RUN_CANCEL_REQUESTED_META_KEY].as_boolean(), False).is_(False),
                        )
                        .values(**values)
                    )
                    if result.rowcount == 0:
                        s.rollback()
                        self._cancelled = True
                        self._cancel_reason = "Task resource was deleted"
                        raise TaskCancellationRequested(self._cancel_reason)
                    s.commit()
                    begin_write_transaction(s)
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

    def complete_transactionally(self, session, result: TaskResult) -> None:
        """Commit successful output and its execution outcome in one transaction.

        The guarded update serializes completion against cancellation. If the
        process exits just after commit, recovery sees a completed run rather
        than downloading an already committed replacement again.
        """
        if result.outcome != "succeeded":
            raise ValueError("Transactional completion requires successful output")
        session.flush()
        changed = session.execute(
            update(TaskRun).where(
                TaskRun.id == self.run_id, TaskRun.status == TaskStatus.RUNNING,
                func.coalesce(TaskRun.meta[RUN_CANCEL_REQUESTED_META_KEY].as_boolean(), False).is_(False),
            ).values(
                status=TaskStatus.SUCCEEDED, progress=100, result=result.as_dict(),
                message=result.summary, last_error=None, next_retry_at=None,
                finished_at=datetime.now(timezone.utc),
            ).execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            raise DownloadCancelled("Download was canceled before publication committed")
        refresh_operations_for_run(session, self.run_id)

    def set_wait_state(self, reason: str | None, message: str | None = None, *, until: float | None = None) -> None:
        """Persist transient worker waiting state without changing worker progress."""
        s = get_session()
        last_operational_error: OperationalError | None = None
        try:
            for i in range(3):
                try:
                    begin_write_transaction(s)
                    current_meta = s.execute(
                        select(TaskRun.meta).where(TaskRun.id == self.run_id)
                    ).scalar_one_or_none()
                    if current_meta is None:
                        exists = s.execute(
                            select(TaskRun.id).where(TaskRun.id == self.run_id)
                        ).scalar_one_or_none()
                        if exists is None:
                            return

                    if not _run_has_active_operation_owner(s, self.run_id):
                        return

                    merged_meta = dict(current_meta or {})
                    if reason:
                        merged_meta[TASK_RUN_WAIT_STATE_META_KEY] = {
                            "reason": reason,
                            "message": message,
                            "until": until,
                        }
                    else:
                        merged_meta.pop(TASK_RUN_WAIT_STATE_META_KEY, None)

                    result = s.execute(
                        update(TaskRun)
                        .where(
                            TaskRun.id == self.run_id,
                            TaskRun.status == TaskStatus.RUNNING,
                            func.coalesce(TaskRun.meta[RUN_CANCEL_REQUESTED_META_KEY].as_boolean(), False).is_(False),
                        )
                        .values(meta=merged_meta or None)
                    )
                    if result.rowcount == 0:
                        s.rollback()
                        return
                    s.commit()
                    begin_write_transaction(s)
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

    if schedule_id is not None:
        sch = session.get(TaskSchedule, schedule_id)
        if sch and sch.max_retries is not None:
            return int(sch.max_retries)

    td = session.execute(select(TaskDefinition).where(TaskDefinition.key == def_key)).scalar_one()
    if td.default_max_retries is not None:
        return int(td.default_max_retries)

    return int(get_settings().scheduler.default_max_retries)


def _backoff_delay(attempt: int) -> float:
    base = float(get_settings().scheduler.retry_backoff_seconds)
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
        tracks_progress: bool,
        kwargs: dict[str, Any],
) -> _PreparedExecution | None:
    """Persist the RUNNING attempt, then release its Session before worker code runs."""
    session = get_session()
    try:
        begin_write_transaction(session)
        if operation_ids and not operation_ids_allow_execution(session, operation_ids):
            return None

        if schedule_id is not None and session.get(TaskSchedule, schedule_id) is None:
            return None

        if run_id is not None:
            run = session.get(TaskRun, run_id)
            if run is None:
                return None
            if run_cancel_requested(run):
                _mark_run_canceled(run, run_cancel_reason(run))
                run.finished_at = datetime.now(timezone.utc)
                session.commit()
                begin_write_transaction(session)
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
                progress=0 if tracks_progress else None,
                result=None,
                attempt_count=0,
                started_at=datetime.now(timezone.utc),
                meta={"inputs": dict(kwargs)} if kwargs else None,
            )
            session.add(run)
            session.flush()

        run_meta = dict(run.meta or {})
        run_meta.pop(TASK_RUN_WAIT_STATE_META_KEY, None)
        run_meta.pop(TASK_RUN_PROGRESS_META_KEY, None)
        run.meta = run_meta or None

        linked_operation_ids = link_run_to_operations(
            session,
            run=run,
            task_key=def_key,
            operation_ids=operation_ids,
            operation_slot=operation_slot,
        )

        run.max_retries = _resolve_max_retries(session, def_key, schedule_id, max_retries)
        if not tracks_progress:
            run.progress = None
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
        begin_write_transaction(session)
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
    """Persist terminal/retry state using a fresh short-lived Session."""
    session = get_session()
    retry_at: datetime | None = None
    terminal_error: Exception | None = None
    try:
        begin_write_transaction(session)
        run = session.get(TaskRun, prepared.run_id)
        if run is None:
            return None, None

        run_meta = dict(run.meta or {})
        run_meta.pop(TASK_RUN_WAIT_STATE_META_KEY, None)
        run_meta.pop(TASK_RUN_PROGRESS_META_KEY, None)
        run.meta = run_meta or None
        if run.status == TaskStatus.SUCCEEDED:
            # A publishing worker already committed artifacts and outcome in one
            # transaction. A late callback/cleanup error cannot revoke success.
            run.runtime_ms = runtime_ms
            session.commit()
            return None, None

        if run_cancel_requested(run):
            cancellation_reason = run_cancel_reason(run, cancellation_reason or "Canceled")
        elif cancellation_reason is None and not _run_has_active_operation_owner(session, run.id):
            cancellation_reason = "Owning operation was canceled"

        if cancellation_reason is not None:
            _mark_run_canceled(run, cancellation_reason)
        elif worker_error is None:
            if isinstance(worker_result, TaskResult):
                run.result = worker_result.as_dict()
                run.message = worker_result.summary
            incomplete = isinstance(worker_result, TaskResult) and worker_result.outcome != "succeeded"
            run.status = TaskStatus.FAILED if incomplete else TaskStatus.SUCCEEDED
            run.progress = 100
            if not run.message:
                run.message = "OK"
            run.last_error = worker_result.summary if incomplete else None
            run.next_retry_at = None
        else:
            run.last_error = str(worker_error)
            if run.attempt_count <= run.max_retries:
                delay = _backoff_delay(run.attempt_count)
                retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                run.next_retry_at = retry_at
                run.status = TaskStatus.RETRY_SCHEDULED
                run.message = (
                    f"Retry {run.attempt_count}/{run.max_retries} scheduled in {int(delay)}s"
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
        begin_write_transaction(session)
        refresh_operations_for_run(session, run.id)
        session.commit()
        return retry_at, terminal_error
    finally:
        session.close()


def request_wait_message(reason: str) -> str:
    return {
        "daily_wire_request_cooldown": "Waiting for The Daily Wire request cooldown",
        "daily_wire_request_queue": "Waiting for a turn to request The Daily Wire",
        "request_spacing": "Waiting for request spacing",
        "upstream_retry": "Waiting for The Daily Wire retry interval",
        "retry_backoff": "Waiting to retry the request",
    }.get(reason, "Waiting for an external dependency")


def _execution_request_priority(operation_ids: tuple[str, ...]):
    if not operation_ids:
        return "background"
    session = get_session()
    try:
        operations = list(session.scalars(select(TaskOperation).where(TaskOperation.id.in_(operation_ids))))
        if any((item.context or {}).get("request_priority") == "bulk" or "bulk" in item.kind or "redownload" in item.kind for item in operations):
            return "bulk"
        return "interactive" if any(item.source == "UI" for item in operations) else "background"
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
        _scheduled_work_pause_token: str | None = None,
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

    task_meta, fn = get_task(def_key)
    preparation_pause = None
    dispatch_pause_token = _scheduled_work_pause_token
    if task_meta.pauses_scheduled_work:
        if run_id is not None:
            scheduler.pause_scheduled_work(
                task_meta.title,
                owner_key=f"task-run:{run_id}",
            )
        elif dispatch_pause_token is None:
            # Direct executor calls do not pass through trigger_now(). Hold a
            # temporary lease before touching execution state, then hand it off
            # to a retry-stable task-run owner once the run has been persisted.
            preparation_pause = scheduler.pause_scheduled_work(task_meta.title)

    try:
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
            tracks_progress=task_meta.tracks_progress,
            kwargs=dict(kwargs),
        )
    except Exception:
        if dispatch_pause_token is not None:
            scheduler.release_scheduled_work_pause(token=dispatch_pause_token)
        if preparation_pause is not None:
            preparation_pause.release()
        elif task_meta.pauses_scheduled_work and run_id is not None:
            scheduler.release_scheduled_work_pause(
                owner_key=f"task-run:{run_id}"
            )
        raise

    if prepared is None:
        if dispatch_pause_token is not None:
            scheduler.release_scheduled_work_pause(token=dispatch_pause_token)
        if preparation_pause is not None:
            preparation_pause.release()
        elif task_meta.pauses_scheduled_work and run_id is not None:
            scheduler.release_scheduled_work_pause(
                owner_key=f"task-run:{run_id}"
            )
        return

    if task_meta.pauses_scheduled_work and run_id is None:
        scheduler.pause_scheduled_work(
            task_meta.title,
            owner_key=f"task-run:{prepared.run_id}",
        )
        if dispatch_pause_token is not None:
            scheduler.release_scheduled_work_pause(token=dispatch_pause_token)
        if preparation_pause is not None:
            preparation_pause.release()

    updater = ProgressUpdater(prepared.run_id, tracks_progress=task_meta.tracks_progress)
    worker_result: Any = None
    worker_error: Exception | None = None
    cancellation_reason: str | None = None
    started_perf = time.perf_counter()

    # Re-check after the TaskRun and operation links are committed. Cancellation
    # can happen after the initial preflight but before this durable handoff.
    if prepared.linked_operation_ids:
        ownership_session = get_session()
        try:
            if not _run_has_active_operation_owner(
                ownership_session,
                prepared.run_id,
            ):
                cancellation_reason = "Owning operation was canceled"
        finally:
            ownership_session.close()

    def on_request_wait(event: RequestWait | None) -> None:
        updater.set_wait_state(
            event.reason if event else None,
            request_wait_message(event.reason) if event else None,
            until=event.until if event else None,
        )

    try:
        if cancellation_reason is None:
            with (
                operation_context(prepared.linked_operation_ids),
                request_context(
                    observer=on_request_wait, should_cancel=updater,
                    priority=_execution_request_priority(prepared.linked_operation_ids),
                ),
            ):
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
    except (TaskCancellationRequested, DownloadCancelled, RequestCancelled) as exc:
        cancellation_reason = str(exc) or "Canceled"
    except Exception as exc:
        if is_no_internet_error(exc):
            logger.warning(NO_INTERNET_CONNECTION_MESSAGE)
            worker_error = NoInternetConnectionError()
            worker_error.__cause__ = exc
        else:
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

    if task_meta.terminal_callback is not None:
        try:
            task_meta.terminal_callback(
                task_key=def_key,
                resource_type=resource_type,
                resource_id=resource_id,
                task_run_id=prepared.run_id,
            )
        except Exception:
            # A post-terminal queue/backfill hook must never rewrite the outcome
            # of the TaskRun that has already been durably finalized.
            logger.exception("Terminal callback failed for task %s run %s", def_key, prepared.run_id)

    if task_meta.pauses_scheduled_work:
        scheduler.release_scheduled_work_pause(
            owner_key=f"task-run:{prepared.run_id}"
        )

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
