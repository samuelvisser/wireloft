from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from backend.db.core import get_session
from task_manager.scheduler.db import (
    TaskDefinition,
    TaskOperation,
    TaskOperationDependency,
    TaskOperationRun,
    TaskOperationTarget,
    TaskRun,
)
from task_manager.scheduler.transactional import queue_task_after_commit
from task_manager.scheduler.types import (
    OperationDependencyCancelPolicy,
    OperationStatus,
    TaskStatus,
)


if TYPE_CHECKING:
    from task_manager.scheduler.operations import OperationSnapshot


logger = logging.getLogger(__name__)
RUN_CANCEL_REQUESTED_META_KEY = "_operation_cancel_requested"
RUN_CANCEL_REASON_META_KEY = "_operation_cancel_reason"
OPERATION_CANCEL_REQUESTED_CONTEXT_KEY = "cancel_requested"

_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
}
_ACTIVE_TASK_STATUSES = {
    TaskStatus.SCHEDULED,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.RETRY_SCHEDULED,
}


def _operation_context_cancel_requested(context: object) -> bool:
    return (
        isinstance(context, dict)
        and context.get(OPERATION_CANCEL_REQUESTED_CONTEXT_KEY) is True
    )


def operation_cancel_requested(operation: TaskOperation) -> bool:
    """Return whether cancellation is durably authoritative for an operation."""
    return _operation_context_cancel_requested(operation.context)


def operation_ids_allow_execution(session: Session, operation_ids: Iterable[str]) -> bool:
    """Return whether explicitly operation-owned work should still execute.

    Status alone is not enough: aggregate refreshes can race cancellation and
    briefly persist a stale active status. The durable cancellation marker is
    authoritative across that handoff.
    """
    ids = tuple(dict.fromkeys(str(value) for value in operation_ids if value))
    if not ids:
        return True
    rows = session.execute(
        select(TaskOperation.status, TaskOperation.context).where(TaskOperation.id.in_(ids))
    ).all()
    return any(
        status in _ACTIVE_OPERATION_STATUSES
        and not _operation_context_cancel_requested(context)
        for status, context in rows
    )


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


def _run_terminal_callbacks(callbacks: Iterable) -> None:
    """Run post-terminal queue hooks without changing an already-durable outcome."""
    for callback in callbacks:
        try:
            callback()
        except Exception:
            logger.exception("Task terminal callback failed after cancellation")


def cancel_operation(
        operation_id: str,
        *,
        reason: str = "Canceled by user",
        acknowledge: bool = True,
) -> OperationSnapshot | None:
    """Cancel a high-level operation and every exclusively owned pending/running run.

    UI-initiated cancellation is acknowledged by the request itself. System
    cancellation (for example the stalled-work watchdog) leaves the notification
    unseen so OperationNotifier can explain why the work stopped.
    """
    session = get_session()
    cancelable_run_ids: set[int] = set()
    released_run_ids: set[int] = set()
    released_definition_ids: set[int] = set()
    terminal_callbacks: set = set()
    try:
        operation = _load_operation(session, operation_id)
        if operation is None:
            return None
        if operation.status not in _ACTIVE_OPERATION_STATUSES:
            raise ValueError("Only an active operation can be canceled")

        completed = sum(
            dependency.child_operation is None
            or dependency.child_operation.status not in _ACTIVE_OPERATION_STATUSES
            for dependency in operation.dependencies
        )
        dependent_children_to_cancel: set[str] = set()
        for dependency in operation.dependencies:
            child = dependency.child_operation
            if (
                child is not None
                and child.status in _ACTIVE_OPERATION_STATUSES
                and not operation_cancel_requested(child)
                and dependency.cancel_policy == OperationDependencyCancelPolicy.CANCEL_IF_EXCLUSIVE.value
                and not _dependency_shared_with_other_active_parent(
                    session,
                    child.id,
                    operation.id,
                )
            ):
                dependent_children_to_cancel.add(child.id)

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
                        released_run_ids.add(run.id)
                        released_definition_ids.add(run.definition_id)

        runs = [link.task_run for target in operation.targets for link in target.run_links if link.task_run is not None]
        if operation.kind == "media.download" and runs and all(_task_status(run.status) == TaskStatus.SUCCEEDED for run in runs):
            session.rollback()
            raise ValueError("The download has already been published")
        cleaning_up = operation.kind == "media.download" and any(
            run.id in cancelable_run_ids and _task_status(run.status) == TaskStatus.RUNNING for run in runs
        )
        now = datetime.now(timezone.utc)
        operation.context = {
            **(operation.context or {}),
            OPERATION_CANCEL_REQUESTED_CONTEXT_KEY: True,
        }
        operation.status = OperationStatus.RUNNING.value if cleaning_up else OperationStatus.CANCELED.value
        if not cleaning_up:
            operation.completion_progress = 100
        operation.message = "Canceling download" if cleaning_up else reason
        operation.result = {
            "summary": reason,
            "data": {
                "completed": completed,
                "total": len(operation.targets) + len(operation.dependencies),
            },
        }
        operation.error = None
        operation.notification_seen_at = now if acknowledge else None
        operation.finished_at = None if cleaning_up else now
        session.flush()
        terminal_callbacks = _terminal_callbacks_for_definition_ids(
            session,
            released_definition_ids,
        )
        session.commit()
    finally:
        session.close()

    from task_manager.scheduler.scheduler import (
        cancel_pending_operation_jobs,
        release_scheduled_work_pause,
    )

    cancel_pending_operation_jobs(
        operation_id=operation_id,
        run_ids=cancelable_run_ids,
    )
    for run_id in released_run_ids:
        release_scheduled_work_pause(owner_key=f"task-run:{run_id}")
    _run_terminal_callbacks(terminal_callbacks)

    for child_operation_id in dependent_children_to_cancel:
        # Another parent can attach to the same independently meaningful child
        # after our transaction commits. Re-check exclusivity immediately before
        # cascading so cancel_if_exclusive can never knowingly stop shared work.
        check_session = get_session()
        try:
            child = check_session.get(TaskOperation, child_operation_id)
            still_exclusive = (
                child is not None
                and child.status in _ACTIVE_OPERATION_STATUSES
                and not operation_cancel_requested(child)
                and not _dependency_shared_with_other_active_parent(
                    check_session,
                    child_operation_id,
                    operation_id,
                )
            )
        finally:
            check_session.close()
        if not still_exclusive:
            continue
        try:
            cancel_operation(
                child_operation_id,
                reason=f"Parent operation canceled: {reason}",
                acknowledge=True,
            )
        except ValueError:
            # The child may have reached a terminal state while the parent
            # cancellation transaction was committing.
            pass

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
    callbacks: set = set()
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
        changed = session.execute(update(TaskRun).where(
            TaskRun.id == run_id, TaskRun.status.in_(_ACTIVE_TASK_STATUSES),
        ).values(
            meta=meta, status=TaskStatus.CANCELED, message=reason,
            last_error=None, next_retry_at=None, finished_at=datetime.now(timezone.utc),
        ).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            session.rollback()
            return False
        session.commit()

        from task_manager.scheduler.operations import refresh_operations_for_run

        refresh_operations_for_run(session, run.id)
        session.commit()
        if not was_running:
            callbacks = _terminal_callbacks_for_definition_ids(session, {definition_id})
    finally:
        session.close()

    from task_manager.scheduler.scheduler import (
        cancel_pending_task_run_jobs,
        release_scheduled_work_pause,
    )

    cancel_pending_task_run_jobs((run_id,))
    if not was_running:
        release_scheduled_work_pause(owner_key=f"task-run:{run_id}")
    _run_terminal_callbacks(callbacks)
    return True


def restart_operation(operation_id: str) -> OperationSnapshot | None:
    """Restart only unfinished logical targets, preserving generic queue policies.

    Ordinary targets are dispatched directly after commit. A task definition may
    instead register a recovery dispatcher when its targets belong to a
    constrained queue (for example the shared media-download concurrency lane).
    Those targets remain QUEUED and the generic dispatcher is invoked after this
    transaction commits, so restart never bypasses the task's scheduling policy.
    """
    from task_manager.scheduler.registry import get_task, task_tracks_progress

    session = get_session()
    cancelable_run_ids: set[int] = set()
    released_run_ids: set[int] = set()
    queue_dispatchers: set = set()
    try:
        operation = _load_operation(session, operation_id)
        if operation is None:
            return None
        if operation.status == OperationStatus.SUCCEEDED.value:
            raise ValueError("A completed operation does not need to be restarted")
        if operation.dependencies:
            raise ValueError(
                "Composite operations are retried by starting a new operation"
            )
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
                    if _task_status(run.status) == TaskStatus.CANCELED:
                        released_run_ids.add(run.id)
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
        completion_progress = int((completed / len(operation.targets)) * 100)
        operation.progress = (
            completion_progress
            if len(operation.targets) > 1
            or task_tracks_progress(operation.targets[0].task_key)
            else None
        )
        operation.completion_progress = completion_progress
        operation.context = {
            key: value
            for key, value in (operation.context or {}).items()
            if key != OPERATION_CANCEL_REQUESTED_CONTEXT_KEY
        }
        operation.message = "Restarting"
        operation.result = None
        operation.error = None
        operation.notification_seen_at = None
        operation.push_notified_at = None
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

    # queue_task_after_commit dispatches replacement workers before commit()
    # returns. Release old critical-task pause leases only after that handoff so
    # a replacement critical job has already acquired its dispatch lease.
    from task_manager.scheduler.scheduler import release_scheduled_work_pause

    for run_id in released_run_ids:
        release_scheduled_work_pause(owner_key=f"task-run:{run_id}")

    # Queue-managed work is dispatched only after the restarted operation is
    # durable. Each dispatcher decides how many slots are available.
    _run_terminal_callbacks(queue_dispatchers)

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

    status = _task_status(run.status)
    if status not in _ACTIVE_TASK_STATUSES:
        return False
    meta = dict(run.meta or {})
    meta[RUN_CANCEL_REQUESTED_META_KEY] = True
    meta[RUN_CANCEL_REASON_META_KEY] = reason
    values = {"meta": meta}
    if status in {TaskStatus.SCHEDULED, TaskStatus.QUEUED, TaskStatus.RETRY_SCHEDULED}:
        values.update(status=TaskStatus.CANCELED, message=reason, next_retry_at=None, finished_at=datetime.now(timezone.utc))
    result = session.execute(
        update(TaskRun).where(
            TaskRun.id == run.id, TaskRun.status.in_(_ACTIVE_TASK_STATUSES),
        ).values(**values).execution_options(synchronize_session=False)
    )
    session.refresh(run)
    return result.rowcount == 1


def _run_shared_with_other_active_operation(
        session: Session,
        run_id: int,
        operation_id: str,
) -> bool:
    rows = session.execute(
        select(TaskOperation.status, TaskOperation.context)
        .join(TaskOperationRun, TaskOperation.id == TaskOperationRun.operation_id)
        .where(
            TaskOperationRun.task_run_id == run_id,
            TaskOperationRun.operation_id != operation_id,
            TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
        )
    ).all()
    return any(
        status in _ACTIVE_OPERATION_STATUSES
        and not _operation_context_cancel_requested(context)
        for status, context in rows
    )


def _dependency_shared_with_other_active_parent(
        session: Session,
        child_operation_id: str,
        parent_operation_id: str,
) -> bool:
    rows = session.execute(
        select(TaskOperation.status, TaskOperation.context)
        .join(
            TaskOperationDependency,
            TaskOperation.id == TaskOperationDependency.parent_operation_id,
        )
        .where(
            TaskOperationDependency.child_operation_id == child_operation_id,
            TaskOperationDependency.parent_operation_id != parent_operation_id,
            TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
        )
    ).all()
    return any(
        status in _ACTIVE_OPERATION_STATUSES
        and not _operation_context_cancel_requested(context)
        for status, context in rows
    )


def _load_operation(session: Session, operation_id: str) -> TaskOperation | None:
    return session.scalar(
        select(TaskOperation)
        .where(TaskOperation.id == operation_id)
        .options(
            selectinload(TaskOperation.targets)
            .selectinload(TaskOperationTarget.run_links)
            .selectinload(TaskOperationRun.task_run),
            selectinload(TaskOperation.dependencies)
            .selectinload(TaskOperationDependency.child_operation),
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