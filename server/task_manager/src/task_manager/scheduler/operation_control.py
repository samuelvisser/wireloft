from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db.core import get_session
from task_manager.scheduler.db import (
    TaskDefinition,
    TaskOperation,
    TaskOperationRun,
    TaskOperationTarget,
    TaskRun,
)
from task_manager.scheduler.transactional import queue_task_after_commit
from task_manager.scheduler.types import OperationStatus, TaskStatus


RUN_CANCEL_REQUESTED_META_KEY = "_operation_cancel_requested"
RUN_CANCEL_REASON_META_KEY = "_operation_cancel_reason"

_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
}
_ACTIVE_TASK_STATUSES = {
    TaskStatus.SCHEDULED,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.RETRY_SCHEDULED,
}


def operation_ids_allow_execution(session: Session, operation_ids: Iterable[str]) -> bool:
    """Return whether explicitly operation-owned work should still execute."""
    ids = tuple(dict.fromkeys(str(value) for value in operation_ids if value))
    if not ids:
        return True
    statuses = session.scalars(
        select(TaskOperation.status).where(TaskOperation.id.in_(ids))
    ).all()
    return any(status in _ACTIVE_OPERATION_STATUSES for status in statuses)


def run_cancel_requested(run: TaskRun) -> bool:
    return (
        isinstance(run.meta, dict)
        and run.meta.get(RUN_CANCEL_REQUESTED_META_KEY) is True
    )


def run_cancel_reason(run: TaskRun, default: str = "Canceled") -> str:
    if isinstance(run.meta, dict):
        reason = run.meta.get(RUN_CANCEL_REASON_META_KEY)
        if isinstance(reason, str) and reason:
            return reason
    return default


def _terminal_callbacks_for_definition_ids(
        session: Session,
        definition_ids: set[int],
) -> set:
    """Resolve generic queue/backfill hooks for synchronously canceled runs."""
    if not definition_ids:
        return set()

    from task_manager.scheduler.registry import get_task

    keys = session.scalars(
        select(TaskDefinition.key).where(TaskDefinition.id.in_(definition_ids))
    ).all()
    callbacks = set()
    for key in keys:
        try:
            task_meta, _ = get_task(key)
        except KeyError:
            continue
        if task_meta.terminal_callback is not None:
            callbacks.add(task_meta.terminal_callback)
    return callbacks


def cancel_operation(
        operation_id: str,
        *,
        reason: str = "Canceled by user",
        acknowledge: bool = True,
) -> dict | None:
    """Cancel a high-level operation and every exclusively owned pending/running run.

    UI-initiated cancellation is acknowledged by the request itself. System
    cancellation (for example the stalled-work watchdog) leaves the notification
    unseen so OperationNotifier can explain why the work stopped.
    """
    session = get_session()
    cancelable_run_ids: set[int] = set()
    released_definition_ids: set[int] = set()
    terminal_callbacks: set = set()
    try:
        operation = _load_operation(session, operation_id)
        if operation is None:
            return None
        if operation.status not in _ACTIVE_OPERATION_STATUSES:
            raise ValueError("Only a queued or running operation can be canceled")

        completed = 0
        for target in operation.targets:
            effective = _effective_run(target)
            if effective is not None and _task_status(effective.status) == TaskStatus.SUCCEEDED:
                completed += 1
            for link in target.run_links:
                run = link.task_run
                if run is None:
                    continue
                if _request_run_cancellation(
                    session,
                    run,
                    operation.id,
                    reason=reason,
                ):
                    cancelable_run_ids.add(run.id)
                    # Pending/retry runs become terminal synchronously, so a
                    # constrained task lane may immediately fill the released
                    # slot. RUNNING workers keep their slot until the executor
                    # reaches its cooperative cancellation boundary and invokes
                    # the same terminal callback itself.
                    if _task_status(run.status) == TaskStatus.CANCELED:
                        released_definition_ids.add(run.definition_id)

        now = datetime.now(timezone.utc)
        operation.status = OperationStatus.CANCELED.value
        operation.message = reason
        operation.result = {
            "summary": reason,
            "data": {
                "completed": completed,
                "total": len(operation.targets),
            },
        }
        operation.error = None
        operation.notification_seen_at = now if acknowledge else None
        operation.finished_at = now
        session.flush()
        terminal_callbacks = _terminal_callbacks_for_definition_ids(
            session,
            released_definition_ids,
        )
        session.commit()
    finally:
        session.close()

    from task_manager.scheduler.scheduler import cancel_pending_operation_jobs

    cancel_pending_operation_jobs(
        operation_id=operation_id,
        run_ids=cancelable_run_ids,
    )
    for callback in terminal_callbacks:
        callback()

    from task_manager.scheduler.operations import get_operation
    return get_operation(operation_id)


def cancel_task_run(run_id: int, *, reason: str) -> bool:
    """Cancel one TaskRun, including an automatic run with no TaskOperation.

    APScheduler cannot terminate a Python thread that is already executing, so a
    running worker is marked terminal immediately and receives a durable
    cooperative cancellation request. Its next progress checkpoint and executor
    finalization both honor that request and cannot resurrect the run.
    """
    session = get_session()
    callback = None
    was_running = False
    try:
        run = session.get(TaskRun, run_id)
        if run is None or _task_status(run.status) not in _ACTIVE_TASK_STATUSES:
            return False

        previous_status = _task_status(run.status)
        was_running = previous_status == TaskStatus.RUNNING
        definition_id = run.definition_id

        meta = dict(run.meta or {})
        meta[RUN_CANCEL_REQUESTED_META_KEY] = True
        meta[RUN_CANCEL_REASON_META_KEY] = reason
        run.meta = meta
        run.status = TaskStatus.CANCELED
        run.message = reason
        run.last_error = None
        run.next_retry_at = None
        run.finished_at = datetime.now(timezone.utc)
        session.commit()

        from task_manager.scheduler.operations import refresh_operations_for_run

        refresh_operations_for_run(session, run.id)
        session.commit()
        if not was_running:
            callbacks = _terminal_callbacks_for_definition_ids(session, {definition_id})
            callback = next(iter(callbacks), None)
    finally:
        session.close()

    from task_manager.scheduler.scheduler import cancel_pending_task_run_jobs

    cancel_pending_task_run_jobs((run_id,))
    if callback is not None:
        callback()
    return True


def restart_operation(operation_id: str) -> dict | None:
    """Restart only unfinished logical targets, preserving generic queue policies.

    Ordinary targets are dispatched directly after commit. A task definition may
    instead register a recovery dispatcher when its targets belong to a
    constrained queue (for example the shared media-download concurrency lane).
    Those targets remain QUEUED and the generic dispatcher is invoked after this
    transaction commits, so restart never bypasses the task's scheduling policy.
    """
    from task_manager.scheduler.registry import get_task

    session = get_session()
    cancelable_run_ids: set[int] = set()
    queue_dispatchers: set = set()
    try:
        operation = _load_operation(session, operation_id)
        if operation is None:
            return None
        if operation.status == OperationStatus.SUCCEEDED.value:
            raise ValueError("A completed operation does not need to be restarted")
        if not operation.targets:
            raise ValueError("This operation has no work to restart")

        targets_to_dispatch: list[TaskOperationTarget] = []
        completed = 0
        for target in operation.targets:
            successful_links = [
                link
                for link in target.run_links
                if link.task_run is not None
                and _task_status(link.task_run.status) == TaskStatus.SUCCEEDED
            ]
            keep_link = max(
                successful_links,
                key=lambda link: link.task_run_id,
                default=None,
            )
            if keep_link is not None:
                completed += 1

            for link in list(target.run_links):
                if keep_link is not None and link is keep_link:
                    continue
                run = link.task_run
                if run is not None and _request_run_cancellation(
                    session,
                    run,
                    operation.id,
                    reason="Replaced by restarted operation",
                ):
                    cancelable_run_ids.add(run.id)
                session.delete(link)

            if keep_link is None:
                targets_to_dispatch.append(target)

        # Remove still-pending APScheduler jobs before the operation becomes active
        # again, otherwise an old queued dispatch and the replacement could race.
        from task_manager.scheduler.scheduler import cancel_pending_operation_jobs

        cancel_pending_operation_jobs(
            operation_id=operation_id,
            run_ids=cancelable_run_ids,
        )

        operation.status = OperationStatus.QUEUED.value
        operation.progress = int((completed / len(operation.targets)) * 100)
        operation.message = "Restarting"
        operation.result = None
        operation.error = None
        operation.notification_seen_at = None
        operation.finished_at = None
        session.flush()

        for target in targets_to_dispatch:
            task_meta, _ = get_task(target.task_key)
            if task_meta.recovery_dispatcher is not None:
                queue_dispatchers.add(task_meta.recovery_dispatcher)
                continue
            queue_task_after_commit(
                session,
                def_key=target.task_key,
                resource_type=target.resource_type,
                resource_id=target.resource_id,
                operation_ids=(operation.id,),
                operation_slot=target.slot_key,
                **dict(target.task_kwargs or {}),
            )

        session.commit()
    finally:
        session.close()

    # Queue-managed work is dispatched only after the restarted operation is
    # durable. Each dispatcher decides how many slots are available.
    for dispatcher in queue_dispatchers:
        dispatcher()

    from task_manager.scheduler.operations import get_operation
    return get_operation(operation_id)


def _request_run_cancellation(
        session: Session,
        run: TaskRun,
        operation_id: str,
        *,
        reason: str,
) -> bool:
    """Request cancellation when this operation exclusively owns the TaskRun."""
    if _run_shared_with_other_active_operation(session, run.id, operation_id):
        return False

    meta = dict(run.meta or {})
    meta[RUN_CANCEL_REQUESTED_META_KEY] = True
    meta[RUN_CANCEL_REASON_META_KEY] = reason
    run.meta = meta

    status = _task_status(run.status)
    if status in {TaskStatus.SCHEDULED, TaskStatus.QUEUED, TaskStatus.RETRY_SCHEDULED}:
        run.status = TaskStatus.CANCELED
        run.message = reason
        run.next_retry_at = None
        run.finished_at = datetime.now(timezone.utc)
    return True


def _run_shared_with_other_active_operation(
        session: Session,
        run_id: int,
        operation_id: str,
) -> bool:
    return session.scalar(
        select(TaskOperationRun.task_run_id)
        .join(TaskOperation, TaskOperation.id == TaskOperationRun.operation_id)
        .where(
            TaskOperationRun.task_run_id == run_id,
            TaskOperationRun.operation_id != operation_id,
            TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
        )
        .limit(1)
    ) is not None


def _load_operation(session: Session, operation_id: str) -> TaskOperation | None:
    return session.scalar(
        select(TaskOperation)
        .where(TaskOperation.id == operation_id)
        .options(
            selectinload(TaskOperation.targets)
            .selectinload(TaskOperationTarget.run_links)
            .selectinload(TaskOperationRun.task_run)
        )
        .execution_options(populate_existing=True)
    )


def _effective_run(target: TaskOperationTarget) -> TaskRun | None:
    runs = [link.task_run for link in target.run_links if link.task_run is not None]
    successful = [run for run in runs if _task_status(run.status) == TaskStatus.SUCCEEDED]
    if successful:
        return max(successful, key=lambda run: run.id)
    return max(runs, key=lambda run: run.id) if runs else None


def _task_status(value) -> TaskStatus:
    return value if isinstance(value, TaskStatus) else TaskStatus(value)
