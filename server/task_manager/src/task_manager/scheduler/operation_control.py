from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db.core import get_session
from task_manager.scheduler.db import TaskOperation, TaskOperationRun, TaskOperationTarget, TaskRun
from task_manager.scheduler.transactional import queue_task_after_commit
from task_manager.scheduler.types import OperationStatus, TaskStatus


RUN_CANCEL_REQUESTED_META_KEY = "_operation_cancel_requested"

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


def cancel_operation(operation_id: str) -> dict | None:
    session = get_session()
    run_ids: set[int] = set()
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
                run_ids.add(run.id)
                _request_run_cancellation(session, run, operation.id)

        now = datetime.now(timezone.utc)
        operation.status = OperationStatus.CANCELED.value
        operation.message = "Canceled by user"
        operation.result = {
            "summary": "Canceled by user",
            "data": {
                "completed": completed,
                "total": len(operation.targets),
            },
        }
        operation.error = None
        operation.finished_at = now
        session.commit()
    finally:
        session.close()

    from task_manager.scheduler.scheduler import cancel_pending_operation_jobs

    cancel_pending_operation_jobs(operation_id=operation_id, run_ids=run_ids)
    from task_manager.scheduler.operations import get_operation
    return get_operation(operation_id)


def restart_operation(operation_id: str) -> dict | None:
    """Restart only the unfinished logical targets of an existing operation."""
    session = get_session()
    old_run_ids: set[int] = set()
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
                if run is not None:
                    old_run_ids.add(run.id)
                    _request_run_cancellation(session, run, operation.id)
                session.delete(link)

            if keep_link is None:
                targets_to_dispatch.append(target)

        # Remove still-pending APScheduler jobs before the operation becomes active
        # again, otherwise an old queued dispatch and the replacement could race.
        from task_manager.scheduler.scheduler import cancel_pending_operation_jobs

        cancel_pending_operation_jobs(operation_id=operation_id, run_ids=old_run_ids)

        operation.status = OperationStatus.QUEUED.value
        operation.progress = int((completed / len(operation.targets)) * 100)
        operation.message = "Restarting"
        operation.result = None
        operation.error = None
        operation.notification_seen_at = None
        operation.finished_at = None
        session.flush()

        for target in targets_to_dispatch:
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

    from task_manager.scheduler.operations import get_operation
    return get_operation(operation_id)


def _request_run_cancellation(session: Session, run: TaskRun, operation_id: str) -> None:
    if _run_shared_with_other_active_operation(session, run.id, operation_id):
        return

    meta = dict(run.meta or {})
    meta[RUN_CANCEL_REQUESTED_META_KEY] = True
    run.meta = meta

    status = _task_status(run.status)
    if status in {TaskStatus.SCHEDULED, TaskStatus.QUEUED, TaskStatus.RETRY_SCHEDULED}:
        run.status = TaskStatus.CANCELED
        run.message = "Canceled by user"
        run.next_retry_at = None
        run.finished_at = datetime.now(timezone.utc)


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
