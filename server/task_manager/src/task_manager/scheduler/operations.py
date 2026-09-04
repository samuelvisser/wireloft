from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.core import get_session
from task_manager.scheduler.db import (
    TaskDefinition,
    TaskOperation,
    TaskOperationRun,
    TaskOperationTarget,
    TaskRun,
)
from task_manager.scheduler.types import OperationSource, OperationStatus, TaskStatus


_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
}
_TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELED,
}
_ACTIVE_TASK_STATUSES = {
    TaskStatus.SCHEDULED,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.RETRY_SCHEDULED,
}


@dataclass(frozen=True)
class OperationTargetSpec:
    task_key: str
    resource_type: str
    resource_id: int | None
    task_kwargs: dict[str, Any] = field(default_factory=dict)
    slot_key: str | None = None
    recover_on_restart: bool = True

    def resolved_slot_key(self) -> str:
        if self.slot_key:
            return self.slot_key
        resource_id = "none" if self.resource_id is None else str(self.resource_id)
        return f"{self.task_key}:{self.resource_type}:{resource_id}"


def create_operation(
        session: Session,
        *,
        kind: str,
        source: str = OperationSource.UI.value,
        resource_type: str,
        resource_id: int | None,
        title: str,
        targets: Sequence[OperationTargetSpec],
        context: dict[str, Any] | None = None,
) -> TaskOperation:
    """Create one durable high-level operation and its logical worker targets."""
    operation = TaskOperation(
        id=str(uuid4()),
        kind=kind,
        source=source,
        resource_type=resource_type,
        resource_id=resource_id,
        title=title,
        status=OperationStatus.QUEUED.value,
        progress=0,
        context=dict(context or {}),
    )
    session.add(operation)
    session.flush()

    created_targets: list[TaskOperationTarget] = []
    for spec in targets:
        target = TaskOperationTarget(
            operation_id=operation.id,
            task_key=spec.task_key,
            resource_type=spec.resource_type,
            resource_id=spec.resource_id,
            slot_key=spec.resolved_slot_key(),
            task_kwargs=dict(spec.task_kwargs or {}),
            recover_on_restart=spec.recover_on_restart,
        )
        session.add(target)
        created_targets.append(target)
    session.flush()

    # A UI request may overlap work WireLoft already started automatically. Link
    # compatible active runs immediately so the existing worker can satisfy the
    # operation instead of forcing the UI to maintain a separate correlation ID.
    for target in created_targets:
        active_run = _matching_active_run(session, target)
        if active_run is not None:
            _link_target_to_run(session, target, active_run)

    refresh_operation(session, operation.id)
    return operation


def operation_target_needs_dispatch(
        session: Session,
        operation_id: str,
        slot_key: str,
) -> bool:
    """Whether a newly created target still needs a worker to be dispatched.

    A target can already be linked when an equivalent automatic worker was
    running before the UI action was requested. Callers can then skip emitting a
    duplicate event and simply let the existing run satisfy the operation.
    """
    target = session.scalar(
        select(TaskOperationTarget).where(
            TaskOperationTarget.operation_id == operation_id,
            TaskOperationTarget.slot_key == slot_key,
        )
    )
    if target is None:
        return False
    return _latest_run_for_target(session, target.id) is None


def complete_operation(
        session: Session,
        operation_id: str,
        *,
        summary: str,
        data: dict[str, Any] | None = None,
) -> TaskOperation | None:
    """Complete an operation that legitimately has no worker targets to execute."""
    operation = session.get(TaskOperation, operation_id)
    if operation is None:
        return None
    now = datetime.now(timezone.utc)
    operation.status = OperationStatus.SUCCEEDED.value
    operation.progress = 100
    operation.message = summary
    operation.result = {"summary": summary, "data": dict(data or {})}
    operation.error = None
    operation.started_at = operation.started_at or now
    operation.finished_at = now
    return operation


def link_run_to_operations(
        session: Session,
        *,
        run: TaskRun,
        task_key: str,
        operation_ids: Iterable[str] = (),
        operation_slot: str | None = None,
) -> tuple[str, ...]:
    """Attach a TaskRun to every operation target it can satisfy.

    Explicit operation IDs are infrastructure context passed by the dispatcher.
    Independently, compatible active targets are discovered by task/resource and
    task inputs, allowing automatic WireLoft work to satisfy an overlapping UI
    request without any worker-specific request-ID plumbing.
    """
    explicit_ids = tuple(dict.fromkeys(str(value) for value in operation_ids if value))
    targets: dict[int, TaskOperationTarget] = {}

    if explicit_ids:
        statement = select(TaskOperationTarget).where(
            TaskOperationTarget.operation_id.in_(explicit_ids),
            TaskOperationTarget.task_key == task_key,
            TaskOperationTarget.resource_type == _resource_type_value(run.resource_type),
            TaskOperationTarget.resource_id == run.resource_id,
        )
        if operation_slot is not None:
            statement = statement.where(TaskOperationTarget.slot_key == operation_slot)
        for target in session.scalars(statement):
            if _run_matches_target_inputs(run, target):
                targets[target.id] = target

    auto_statement = (
        select(TaskOperationTarget)
        .join(TaskOperation, TaskOperation.id == TaskOperationTarget.operation_id)
        .where(
            TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
            TaskOperationTarget.task_key == task_key,
            TaskOperationTarget.resource_type == _resource_type_value(run.resource_type),
            TaskOperationTarget.resource_id == run.resource_id,
        )
    )
    for target in session.scalars(auto_statement):
        if _run_matches_target_inputs(run, target):
            targets[target.id] = target

    operation_ids_touched: set[str] = set()
    for target in targets.values():
        _link_target_to_run(session, target, run)
        operation_ids_touched.add(target.operation_id)

    session.flush()
    for operation_id in operation_ids_touched:
        refresh_operation(session, operation_id)
    return tuple(sorted(operation_ids_touched))


def refresh_operations_for_run(session: Session, task_run_id: int) -> None:
    operation_ids = set(
        session.scalars(
            select(TaskOperationRun.operation_id).where(
                TaskOperationRun.task_run_id == task_run_id
            )
        )
    )
    for operation_id in operation_ids:
        refresh_operation(session, operation_id)


def refresh_operation(session: Session, operation_id: str) -> TaskOperation | None:
    operation = session.get(TaskOperation, operation_id)
    if operation is None:
        return None

    targets = list(
        session.scalars(
            select(TaskOperationTarget)
            .where(TaskOperationTarget.operation_id == operation_id)
            .order_by(TaskOperationTarget.id.asc())
        )
    )
    if not targets:
        return operation

    effective_runs = [_effective_run_for_target(session, target.id) for target in targets]
    linked_runs = [run for run in effective_runs if run is not None]
    terminal_runs = [run for run in linked_runs if _task_status(run.status) in _TERMINAL_TASK_STATUSES]

    total = len(targets)
    progress_total = 0
    for run in effective_runs:
        if run is None:
            continue
        status = _task_status(run.status)
        if status in _TERMINAL_TASK_STATUSES:
            progress_total += 100
        elif isinstance(run.progress, int):
            progress_total += max(0, min(100, run.progress))
    operation.progress = int(progress_total / total) if total else 0

    starts = [run.started_at for run in linked_runs if run.started_at is not None]
    if starts:
        operation.started_at = min(starts)

    if not linked_runs:
        operation.status = OperationStatus.QUEUED.value
        operation.message = "Queued"
        operation.finished_at = None
        return operation

    if len(terminal_runs) < total:
        operation.status = OperationStatus.RUNNING.value
        operation.finished_at = None
        operation.error = None
        if total == 1:
            operation.message = linked_runs[-1].message or "Running"
        else:
            operation.message = f"{len(terminal_runs)}/{total} tasks finished"
        return operation

    statuses = [_task_status(run.status) for run in terminal_runs]
    succeeded = sum(status == TaskStatus.SUCCEEDED for status in statuses)
    failed = sum(status == TaskStatus.FAILED for status in statuses)
    canceled = sum(status == TaskStatus.CANCELED for status in statuses)

    if succeeded == total:
        operation.status = OperationStatus.SUCCEEDED.value
        operation.error = None
    elif succeeded > 0:
        operation.status = OperationStatus.PARTIAL.value
        operation.error = _first_terminal_error(terminal_runs)
    elif failed > 0:
        operation.status = OperationStatus.FAILED.value
        operation.error = _first_terminal_error(terminal_runs)
    else:
        operation.status = OperationStatus.CANCELED.value
        operation.error = _first_terminal_error(terminal_runs)

    operation.progress = 100
    operation.result = _aggregate_results(terminal_runs, succeeded, failed, canceled, total)
    summary = operation.result.get("summary") if isinstance(operation.result, dict) else None
    operation.message = str(summary or operation.message or "Finished")
    finishes = [run.finished_at for run in terminal_runs if run.finished_at is not None]
    operation.finished_at = max(finishes) if finishes else datetime.now(timezone.utc)
    return operation


def mark_interrupted_operations_for_recovery(
        session: Session,
        interrupted_run_ids: Sequence[int],
) -> None:
    if not interrupted_run_ids:
        return
    operation_ids = set(
        session.scalars(
            select(TaskOperationRun.operation_id).where(
                TaskOperationRun.task_run_id.in_(interrupted_run_ids)
            )
        )
    )
    for operation_id in operation_ids:
        operation = session.get(TaskOperation, operation_id)
        if operation is None or operation.status not in _ACTIVE_OPERATION_STATUSES:
            continue
        operation.status = OperationStatus.QUEUED.value
        operation.message = "Recovering after WireLoft restart"
        operation.finished_at = None
        operation.error = None


def recover_pending_operations() -> int:
    """Requeue incomplete recoverable targets after a process restart.

    Task targets persist the worker key, resource and validated worker inputs, so
    recovery does not need action-specific code or IDs embedded in worker params.
    """
    session = get_session()
    try:
        operations = list(
            session.scalars(
                select(TaskOperation).where(TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES))
            )
        )
        recoveries: list[tuple[str, str, str, int | None, str, dict[str, Any]]] = []
        for operation in operations:
            targets = list(
                session.scalars(
                    select(TaskOperationTarget).where(
                        TaskOperationTarget.operation_id == operation.id,
                        TaskOperationTarget.recover_on_restart.is_(True),
                    )
                )
            )
            for target in targets:
                effective = _effective_run_for_target(session, target.id)
                if effective is not None and _task_status(effective.status) == TaskStatus.SUCCEEDED:
                    continue
                recoveries.append((
                    operation.id,
                    target.task_key,
                    target.resource_type,
                    target.resource_id,
                    target.slot_key,
                    dict(target.task_kwargs or {}),
                ))
                operation.status = OperationStatus.QUEUED.value
                operation.message = "Queued for recovery"
                operation.finished_at = None
        session.commit()
    finally:
        session.close()

    if not recoveries:
        return 0

    from task_manager.scheduler.scheduler import trigger_now

    for operation_id, task_key, resource_type, resource_id, slot_key, task_kwargs in recoveries:
        trigger_now(
            def_key=task_key,
            resource_type=resource_type,
            resource_id=resource_id,
            operation_ids=(operation_id,),
            operation_slot=slot_key,
            **task_kwargs,
        )
    return len(recoveries)


def list_operations(
        *,
        source: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        kind: str | None = None,
        relevant: bool = False,
        limit: int = 100,
) -> list[dict[str, Any]]:
    session = get_session()
    try:
        statement = select(TaskOperation)
        if source is not None:
            statement = statement.where(TaskOperation.source == source)
        if resource_type is not None:
            statement = statement.where(TaskOperation.resource_type == resource_type)
        if resource_id is not None:
            statement = statement.where(TaskOperation.resource_id == resource_id)
        if kind is not None:
            statement = statement.where(TaskOperation.kind == kind)
        if relevant:
            statement = statement.where(
                (TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES))
                | (TaskOperation.notification_seen_at.is_(None))
            )
        operations = list(
            session.scalars(
                statement.order_by(TaskOperation.created_at.desc()).limit(max(1, min(limit, 500)))
            )
        )
        for operation in operations:
            refresh_operation(session, operation.id)
        session.commit()
        return [_operation_to_dict(session, operation) for operation in operations]
    finally:
        session.close()


def get_operation(operation_id: str) -> dict[str, Any] | None:
    session = get_session()
    try:
        operation = refresh_operation(session, operation_id)
        if operation is None:
            return None
        session.commit()
        return _operation_to_dict(session, operation)
    finally:
        session.close()


def mark_operation_seen(operation_id: str) -> dict[str, Any] | None:
    session = get_session()
    try:
        operation = session.get(TaskOperation, operation_id)
        if operation is None:
            return None
        operation.notification_seen_at = datetime.now(timezone.utc)
        session.commit()
        return _operation_to_dict(session, operation)
    finally:
        session.close()


def _operation_to_dict(session: Session, operation: TaskOperation) -> dict[str, Any]:
    targets = list(
        session.scalars(
            select(TaskOperationTarget).where(TaskOperationTarget.operation_id == operation.id)
        )
    )
    effective_runs = [_effective_run_for_target(session, target.id) for target in targets]
    terminal_count = sum(
        run is not None and _task_status(run.status) in _TERMINAL_TASK_STATUSES
        for run in effective_runs
    )
    return {
        "id": operation.id,
        "kind": operation.kind,
        "source": operation.source,
        "resource_type": operation.resource_type,
        "resource_id": operation.resource_id,
        "title": operation.title,
        "status": operation.status,
        "progress": operation.progress,
        "progress_current": terminal_count,
        "progress_total": len(targets),
        "message": operation.message,
        "result": operation.result,
        "context": operation.context,
        "error": operation.error,
        "notification_seen_at": operation.notification_seen_at.isoformat() if operation.notification_seen_at else None,
        "started_at": operation.started_at.isoformat() if operation.started_at else None,
        "finished_at": operation.finished_at.isoformat() if operation.finished_at else None,
        "created_at": operation.created_at.isoformat() if operation.created_at else None,
        "updated_at": operation.updated_at.isoformat() if operation.updated_at else None,
    }


def _matching_active_run(session: Session, target: TaskOperationTarget) -> TaskRun | None:
    statement = (
        select(TaskRun)
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(
            TaskDefinition.key == target.task_key,
            TaskRun.resource_id == target.resource_id,
            TaskRun.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .order_by(TaskRun.id.desc())
    )
    for run in session.scalars(statement):
        if _resource_type_value(run.resource_type) != target.resource_type:
            continue
        if _run_matches_target_inputs(run, target):
            return run
    return None


def _run_matches_target_inputs(run: TaskRun, target: TaskOperationTarget) -> bool:
    expected = dict(target.task_kwargs or {})
    if not expected:
        return True
    inputs = run.meta.get("inputs") if isinstance(run.meta, dict) else None
    if not isinstance(inputs, dict):
        return False
    return all(inputs.get(key) == value for key, value in expected.items())


def _link_target_to_run(session: Session, target: TaskOperationTarget, run: TaskRun) -> None:
    existing = session.get(TaskOperationRun, (target.id, run.id))
    if existing is not None:
        return
    session.add(TaskOperationRun(
        target_id=target.id,
        task_run_id=run.id,
        operation_id=target.operation_id,
    ))


def _latest_run_for_target(session: Session, target_id: int) -> TaskRun | None:
    return session.scalar(
        select(TaskRun)
        .join(TaskOperationRun, TaskOperationRun.task_run_id == TaskRun.id)
        .where(TaskOperationRun.target_id == target_id)
        .order_by(TaskRun.id.desc())
        .limit(1)
    )


def _effective_run_for_target(session: Session, target_id: int) -> TaskRun | None:
    """Return the run that currently determines whether a target is satisfied.

    A logical target may be linked to more than one equivalent run when automatic
    and UI work overlap. Once any linked run succeeds, the requested work is
    satisfied even if another duplicate later fails or is still running. Before
    success, the newest run represents current retry/recovery progress.
    """
    successful = session.scalar(
        select(TaskRun)
        .join(TaskOperationRun, TaskOperationRun.task_run_id == TaskRun.id)
        .where(
            TaskOperationRun.target_id == target_id,
            TaskRun.status == TaskStatus.SUCCEEDED,
        )
        .order_by(TaskRun.id.desc())
        .limit(1)
    )
    return successful or _latest_run_for_target(session, target_id)


def _aggregate_results(
        runs: Sequence[TaskRun],
        succeeded: int,
        failed: int,
        canceled: int,
        total: int,
) -> dict[str, Any]:
    results = [run.result for run in runs if isinstance(run.result, dict)]
    if total == 1 and results:
        return dict(results[0])

    aggregate_data: dict[str, Any] = {
        "completed": succeeded,
        "failed": failed,
        "canceled": canceled,
        "total": total,
    }
    for result in results:
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                aggregate_data[key] = aggregate_data.get(key, 0) + value

    if failed or canceled:
        summary = f"{succeeded}/{total} tasks completed"
    else:
        summary = f"Completed {total} tasks"
    return {"summary": summary, "data": aggregate_data}


def _first_terminal_error(runs: Sequence[TaskRun]) -> str | None:
    for run in runs:
        if run.last_error:
            return run.last_error
        if _task_status(run.status) == TaskStatus.CANCELED and run.message:
            return run.message
    return None


def _resource_type_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _task_status(value: Any) -> TaskStatus:
    return value if isinstance(value, TaskStatus) else TaskStatus(value)
