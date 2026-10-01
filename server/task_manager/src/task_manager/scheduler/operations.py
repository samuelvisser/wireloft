from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Sequence
from uuid import uuid4

from sqlalchemy import select
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
from task_manager.scheduler.operation_control import operation_cancel_requested, run_cancel_requested
from task_manager.scheduler.registry import task_tracks_progress
from task_manager.scheduler.transactional import queue_task_after_commit
from task_manager.scheduler.types import (
    OperationDependencyCancelPolicy,
    OperationSource,
    OperationStatus,
    TaskStatus,
)


TASK_RUN_WAIT_STATE_META_KEY = "_operation_wait_state"
TASK_RUN_PROGRESS_META_KEY = "_progress_meta"
TASK_RUN_COMPLETION_PROGRESS_META_KEY = "_completion_progress"

_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
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


@dataclass(frozen=True)
class OperationDependencySpec:
    child_operation_id: str
    slot_key: str | None = None
    weight: float = 1.0
    required: bool = True
    cancel_policy: str = OperationDependencyCancelPolicy.DETACH.value
    context: dict[str, Any] = field(default_factory=dict)

    def resolved_slot_key(self) -> str:
        return self.slot_key or f"operation:{self.child_operation_id}"

    def validate(self) -> None:
        if not isfinite(float(self.weight)) or float(self.weight) <= 0:
            raise ValueError("Operation dependency weight must be finite and positive")
        try:
            OperationDependencyCancelPolicy(self.cancel_policy)
        except ValueError as exc:
            raise ValueError(f"Unknown operation dependency cancel policy: {self.cancel_policy}") from exc


@dataclass(frozen=True)
class OperationSnapshot:
    id: str
    kind: str
    source: str
    resource_type: str
    resource_id: int | None
    title: str
    status: str
    progress: int | None
    completion_progress: int | None
    progress_current: int
    progress_total: int
    message: str | None
    result: dict[str, Any] | None
    context: dict[str, Any] | None
    progress_meta: dict[str, Any] | None
    error: str | None
    notification_seen_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


def create_operation(
        session: Session,
        *,
        kind: str,
        source: str = OperationSource.UI.value,
        resource_type: str,
        resource_id: int | None,
        title: str,
        targets: Sequence[OperationTargetSpec],
        dependencies: Sequence[OperationDependencySpec] = (),
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
        completion_progress=0,
        context=dict(context or {}),
    )
    session.add(operation)
    session.flush()

    created_targets: list[TaskOperationTarget] = []
    for spec in targets:
        target = TaskOperationTarget(
            operation=operation,
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

    if dependencies:
        add_operation_dependencies(
            session,
            operation.id,
            dependencies,
            refresh=False,
        )

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

    A target can already be linked when equivalent automatic work was running
    before the UI action was requested. Callers can then skip a duplicate worker.
    """
    target = _load_target_with_runs(session, operation_id, slot_key)
    return target is not None and _latest_run_for_target(target) is None


def queue_operation_target_dispatch(
        session: Session,
        operation_id: str,
        slot_key: str,
) -> bool:
    """Queue one operation target for execution after the current transaction commits.

    Dispatching from the durable target avoids fanning a UI operation out through
    hundreds of transient domain events. The operation ID and slot stay scheduler
    infrastructure and are never exposed as worker parameters.
    """
    target = _load_target_with_runs(session, operation_id, slot_key)
    if target is None or _latest_run_for_target(target) is not None:
        return False

    queue_task_after_commit(
        session,
        def_key=target.task_key,
        resource_type=target.resource_type,
        resource_id=target.resource_id,
        operation_ids=(operation_id,),
        operation_slot=target.slot_key,
        **dict(target.task_kwargs or {}),
    )
    return True


def add_operation_dependencies(
        session: Session,
        parent_operation_id: str,
        dependencies: Sequence[OperationDependencySpec],
        *,
        refresh: bool = True,
) -> tuple[TaskOperationDependency, ...]:
    """Attach independently meaningful child operations to one parent.

    Dependency rows are the durable manifest for composite work. They contain
    only orchestration facts; the child operation remains the source of truth
    for its own execution state, progress, result and errors.
    """
    parent = session.get(TaskOperation, parent_operation_id)
    if parent is None:
        raise ValueError("Parent operation does not exist")

    created: list[TaskOperationDependency] = []
    for spec in dependencies:
        spec.validate()
        child = session.get(TaskOperation, spec.child_operation_id)
        if child is None:
            raise ValueError(f"Child operation '{spec.child_operation_id}' does not exist")
        if child.id == parent.id:
            raise ValueError("An operation cannot depend on itself")
        if _operation_depends_on(session, child.id, parent.id):
            raise ValueError("TaskOperation dependencies must form an acyclic graph")

        slot_key = spec.resolved_slot_key()
        existing = session.scalar(
            select(TaskOperationDependency).where(
                TaskOperationDependency.parent_operation_id == parent.id,
                TaskOperationDependency.slot_key == slot_key,
            )
        )
        if existing is not None:
            if existing.child_operation_id != child.id:
                raise ValueError(f"Dependency slot '{slot_key}' already points to another operation")
            created.append(existing)
            continue

        duplicate_child = session.scalar(
            select(TaskOperationDependency).where(
                TaskOperationDependency.parent_operation_id == parent.id,
                TaskOperationDependency.child_operation_id == child.id,
            )
        )
        if duplicate_child is not None:
            raise ValueError("The same child operation cannot be attached twice")

        dependency = TaskOperationDependency(
            parent_operation=parent,
            child_operation=child,
            slot_key=slot_key,
            weight=float(spec.weight),
            required=bool(spec.required),
            cancel_policy=spec.cancel_policy,
            context=dict(spec.context or {}),
        )
        session.add(dependency)
        created.append(dependency)

    session.flush()
    if refresh:
        refresh_operation(session, parent.id)
    return tuple(created)


def _operation_depends_on(
        session: Session,
        operation_id: str,
        possible_descendant_id: str,
) -> bool:
    """Return whether operation_id already reaches possible_descendant_id."""
    frontier = {operation_id}
    visited: set[str] = set()
    while frontier:
        if possible_descendant_id in frontier:
            return True
        visited.update(frontier)
        children = set(session.scalars(
            select(TaskOperationDependency.child_operation_id).where(
                TaskOperationDependency.parent_operation_id.in_(frontier),
                TaskOperationDependency.child_operation_id.is_not(None),
            )
        ))
        frontier = {child_id for child_id in children if child_id and child_id not in visited}
    return False


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
    operation.completion_progress = 100
    operation.message = summary
    operation.result = {"summary": summary, "data": dict(data or {})}
    operation.error = None
    operation.started_at = operation.started_at or now
    operation.finished_at = now
    session.flush()
    _refresh_operation_tree(session, (operation.id,))
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

    The executor commits this lightweight association before refreshing aggregate
    operation state. Keeping the potentially large aggregate read out of the run
    creation transaction prevents fan-out operations from holding SQLite's write
    lock while hundreds of sibling tasks are also starting.
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
        select(TaskOperationTarget, TaskOperation)
        .join(TaskOperation, TaskOperation.id == TaskOperationTarget.operation_id)
        .where(
            TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
            TaskOperationTarget.task_key == task_key,
            TaskOperationTarget.resource_type == _resource_type_value(run.resource_type),
            TaskOperationTarget.resource_id == run.resource_id,
        )
    )
    for target, operation in session.execute(auto_statement):
        if operation_cancel_requested(operation):
            continue
        if _run_matches_target_inputs(run, target):
            targets[target.id] = target

    operation_ids_touched: set[str] = set()
    for target in targets.values():
        _link_target_to_run(session, target, run)
        operation_ids_touched.add(target.operation_id)

    session.flush()
    return tuple(sorted(operation_ids_touched))


def refresh_operations_for_run(session: Session, task_run_id: int) -> None:
    operation_ids = set(
        session.scalars(
            select(TaskOperationRun.operation_id).where(
                TaskOperationRun.task_run_id == task_run_id
            )
        )
    )
    _refresh_operation_tree(session, operation_ids)


def refresh_operation(session: Session, operation_id: str) -> TaskOperation | None:
    refreshed = _refresh_operation_tree(session, (operation_id,))
    return refreshed.get(operation_id)


def _refresh_operation_tree(
        session: Session,
        operation_ids: Iterable[str],
) -> dict[str, TaskOperation]:
    """Refresh operations and every transitive parent dependency exactly once."""
    queue = list(dict.fromkeys(str(value) for value in operation_ids if value))
    visited: set[str] = set()
    refreshed: dict[str, TaskOperation] = {}

    while queue:
        operation_id = queue.pop(0)
        if operation_id in visited:
            continue
        visited.add(operation_id)

        operation = _load_operation_with_runs(session, operation_id)
        if operation is None:
            continue
        refreshed[operation_id] = _refresh_loaded_operation(operation)
        session.flush()

        parent_ids = session.scalars(
            select(TaskOperationDependency.parent_operation_id).where(
                TaskOperationDependency.child_operation_id == operation_id
            )
        )
        queue.extend(parent_id for parent_id in parent_ids if parent_id not in visited)

    return refreshed


def _refresh_loaded_operation(operation: TaskOperation) -> TaskOperation:
    cancel_requested = operation_cancel_requested(operation)
    download_cleanup_active = (
        operation.kind == "media.download"
        and any(
            link.task_run is not None
            and _task_status(link.task_run.status) == TaskStatus.RUNNING
            and run_cancel_requested(link.task_run)
            for target in operation.targets
            for link in target.run_links
        )
    )

    # A cancellation marker survives an aggregate refresh that loaded the old
    # RUNNING/WAITING state just before cancel_operation committed. Generic and
    # composite operations are terminal immediately. media.download deliberately
    # remains RUNNING only while a worker that received the cancellation request
    # is cooperatively cleaning up.
    if cancel_requested and not download_cleanup_active:
        operation.status = OperationStatus.CANCELED.value
        operation.completion_progress = 100
        if isinstance(operation.result, dict):
            summary = operation.result.get("summary")
            if isinstance(summary, str) and summary:
                operation.message = summary
        operation.error = None
        operation.finished_at = operation.finished_at or datetime.now(timezone.utc)
        return operation

    # Preserve older terminal cancellations that predate the marker too.
    if operation.status == OperationStatus.CANCELED.value and operation.finished_at is not None:
        return operation

    if operation.dependencies:
        return _refresh_composite_operation(operation)
    return _refresh_direct_operation(operation)


def _target_tracks_progress(target: TaskOperationTarget) -> bool:
    return task_tracks_progress(target.task_key)


def _direct_progress_is_determinate(targets: Sequence[TaskOperationTarget]) -> bool:
    # Multiple opaque tasks still provide useful aggregate completion progress:
    # 3/10 finished is determinate even when none of the individual workers can
    # report an in-task percentage.
    return len(targets) > 1 or any(_target_tracks_progress(target) for target in targets)


def _composite_progress_is_determinate(
        targets: Sequence[TaskOperationTarget],
        dependencies: Sequence[TaskOperationDependency],
) -> bool:
    total_units = len(targets) + len(dependencies)
    if total_units > 1:
        return True
    if targets:
        return _target_tracks_progress(targets[0])
    if dependencies:
        child = dependencies[0].child_operation
        return child is None or child.progress is not None
    return False


def _refresh_direct_operation(operation: TaskOperation) -> TaskOperation:
    targets = list(operation.targets)
    if not targets:
        return operation

    effective_runs = [_effective_run_for_target(target) for target in targets]
    linked_runs = [run for run in effective_runs if run is not None]
    terminal_runs = [run for run in linked_runs if _task_status(run.status) in _TERMINAL_TASK_STATUSES]

    total = len(targets)
    operation.completion_progress = int(
        sum(_run_completion_progress(run) for run in effective_runs if run is not None) / total
    ) if total else 0

    worker_progress_runs = [
        run
        for run in linked_runs
        if _task_status(run.status) not in _TERMINAL_TASK_STATUSES
        and _run_reports_worker_progress(run)
    ]
    if not _direct_progress_is_determinate(targets) and len(terminal_runs) < total:
        operation.progress = None
    elif worker_progress_runs:
        progress_total = 0
        for run in effective_runs:
            if run is None:
                continue
            status = _task_status(run.status)
            if status in _TERMINAL_TASK_STATUSES:
                progress_total += 100
            elif _run_reports_worker_progress(run):
                progress_total += max(0, min(100, int(run.progress or 0)))
        operation.progress = int(progress_total / total) if total else 0
    else:
        operation.progress = int((len(terminal_runs) / total) * 100) if total else 0

    starts = [run.started_at for run in linked_runs if run.started_at is not None]
    if starts:
        operation.started_at = min(starts)

    if not linked_runs:
        operation.status = OperationStatus.QUEUED.value
        operation.message = "Queued"
        operation.finished_at = None
        return operation

    if len(terminal_runs) < total:
        if operation.kind == "media.download" and operation_cancel_requested(operation):
            operation.status = OperationStatus.RUNNING.value
            operation.message = "Canceling download"
            operation.finished_at = None
            return operation
        operation.finished_at = None
        operation.error = None
        wait_state = next(
            (
                state
                for run in reversed(linked_runs)
                if _task_status(run.status) not in _TERMINAL_TASK_STATUSES
                for state in (_run_wait_state(run),)
                if state is not None
            ),
            None,
        )
        active_runs = [run for run in linked_runs if _task_status(run.status) not in _TERMINAL_TASK_STATUSES]
        all_blocked = active_runs and all(_run_wait_state(run) is not None for run in active_runs)
        running_runs = [
            run for run in active_runs
            if _task_status(run.status) == TaskStatus.RUNNING
        ]
        if wait_state is not None and all_blocked:
            operation.status = OperationStatus.WAITING.value
            message = wait_state.get("message")
            operation.message = message if isinstance(message, str) and message else "Waiting"
        elif not running_runs:
            # SCHEDULED/QUEUED TaskRuns can be durable reservations that have not
            # entered an executor yet. Do not present them as active execution.
            operation.status = OperationStatus.QUEUED.value
            if total == 1:
                operation.message = linked_runs[-1].message or "Queued"
            else:
                operation.message = f"{len(terminal_runs)}/{total} tasks finished; queued"
        else:
            operation.status = OperationStatus.RUNNING.value
            if total == 1:
                operation.message = running_runs[-1].message or "Running"
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
    elif succeeded > 0 or any((run.result or {}).get("outcome") == "partial" for run in terminal_runs):
        operation.status = OperationStatus.PARTIAL.value
        operation.error = _first_terminal_error(terminal_runs)
    elif failed > 0:
        operation.status = OperationStatus.FAILED.value
        operation.error = _first_terminal_error(terminal_runs)
    else:
        operation.status = OperationStatus.CANCELED.value
        operation.error = _first_terminal_error(terminal_runs)

    operation.progress = 100
    operation.completion_progress = 100
    operation.result = _aggregate_results(terminal_runs, succeeded, failed, canceled, total)
    summary = operation.result.get("summary") if isinstance(operation.result, dict) else None
    operation.message = str(summary or operation.message or "Finished")
    finishes = [run.finished_at for run in terminal_runs if run.finished_at is not None]
    operation.finished_at = max(finishes) if finishes else datetime.now(timezone.utc)
    return operation


def _refresh_composite_operation(operation: TaskOperation) -> TaskOperation:
    """Aggregate direct targets and independent child TaskOperations.

    Parent progress is orchestration progress, so dependency weights and child
    completion_progress drive it. A child remains independently visible because
    its own display progress and lifecycle stay on that child operation.
    """
    targets = list(operation.targets)
    dependencies = list(operation.dependencies)
    effective_runs = [_effective_run_for_target(target) for target in targets]

    total_weight = float(len(targets)) + sum(float(dep.weight) for dep in dependencies)
    completed_weight = sum(
        _run_completion_progress(run)
        for run in effective_runs
        if run is not None
    ) / 100.0

    for dependency in dependencies:
        child = dependency.child_operation
        if child is None or child.status not in _ACTIVE_OPERATION_STATUSES:
            fraction = 1.0
        else:
            fraction = max(0.0, min(1.0, float(child.completion_progress or 0) / 100.0))
        completed_weight += float(dependency.weight) * fraction

    aggregate_progress = int(100 * completed_weight / total_weight) if total_weight else 0
    aggregate_progress = max(0, min(100, aggregate_progress))
    operation.progress = (
        aggregate_progress
        if _composite_progress_is_determinate(targets, dependencies)
        else None
    )
    operation.completion_progress = aggregate_progress

    starts = [
        run.started_at for run in effective_runs
        if run is not None and run.started_at is not None
    ]
    starts.extend(
        dep.child_operation.started_at
        for dep in dependencies
        if dep.child_operation is not None and dep.child_operation.started_at is not None
    )
    if starts:
        operation.started_at = min(starts)

    target_terminal = [
        run is not None and _task_status(run.status) in _TERMINAL_TASK_STATUSES
        for run in effective_runs
    ]
    dependency_terminal = [
        dep.child_operation is None
        or dep.child_operation.status not in _ACTIVE_OPERATION_STATUSES
        for dep in dependencies
    ]
    terminal_count = sum(target_terminal) + sum(dependency_terminal)
    total_count = len(targets) + len(dependencies)

    if terminal_count < total_count:
        operation.finished_at = None
        operation.error = None

        active_direct = [
            run for run in effective_runs
            if run is not None and _task_status(run.status) not in _TERMINAL_TASK_STATUSES
        ]
        active_children = [
            dep.child_operation for dep in dependencies
            if dep.child_operation is not None
            and dep.child_operation.status in _ACTIVE_OPERATION_STATUSES
        ]
        has_started = bool(active_direct) or any(
            child.status in {OperationStatus.RUNNING.value, OperationStatus.WAITING.value}
            for child in active_children
        )
        all_blocked = bool(active_direct or active_children) and all(
            _run_wait_state(run) is not None for run in active_direct
        ) and all(
            child.status in {OperationStatus.QUEUED.value, OperationStatus.WAITING.value}
            for child in active_children
        )

        if all_blocked and any(child.status == OperationStatus.WAITING.value for child in active_children):
            operation.status = OperationStatus.WAITING.value
            waiting_child = next(
                (child for child in active_children if child.status == OperationStatus.WAITING.value),
                None,
            )
            operation.message = waiting_child.message if waiting_child and waiting_child.message else "Waiting"
        elif not has_started:
            operation.status = OperationStatus.QUEUED.value
            operation.message = "Queued"
        else:
            operation.status = OperationStatus.RUNNING.value
            operation.message = f"{terminal_count}/{total_count} operations finished"
        return operation

    required_statuses: list[str] = []
    result_payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    finishes: list[datetime] = []

    for run in effective_runs:
        if run is None:
            required_statuses.append(OperationStatus.FAILED.value)
            errors.append("Required task was never created")
            continue
        status = _task_status(run.status)
        required_statuses.append(
            OperationStatus.SUCCEEDED.value if status == TaskStatus.SUCCEEDED
            else OperationStatus.FAILED.value if status == TaskStatus.FAILED
            else OperationStatus.CANCELED.value
        )
        if isinstance(run.result, dict):
            result_payloads.append(run.result)
        if run.finished_at is not None:
            finishes.append(run.finished_at)
        if run.last_error:
            errors.append(run.last_error)
        elif status == TaskStatus.CANCELED and run.message:
            errors.append(run.message)

    for dependency in dependencies:
        child = dependency.child_operation
        if child is not None:
            if isinstance(child.result, dict):
                result_payloads.append(child.result)
            if child.finished_at is not None:
                finishes.append(child.finished_at)
        if not dependency.required:
            continue
        if child is None:
            required_statuses.append(OperationStatus.FAILED.value)
            errors.append("Required child operation was removed")
            continue
        required_statuses.append(child.status)
        if child.status != OperationStatus.SUCCEEDED.value and child.error:
            errors.append(child.error)

    succeeded = sum(status == OperationStatus.SUCCEEDED.value for status in required_statuses)
    failed = sum(status == OperationStatus.FAILED.value for status in required_statuses)
    canceled = sum(status == OperationStatus.CANCELED.value for status in required_statuses)
    partial = sum(status == OperationStatus.PARTIAL.value for status in required_statuses)
    required_total = len(required_statuses)

    if required_total == 0 or succeeded == required_total:
        operation.status = OperationStatus.SUCCEEDED.value
        operation.error = None
    elif partial or succeeded > 0:
        operation.status = OperationStatus.PARTIAL.value
        operation.error = errors[0] if errors else None
    elif failed > 0:
        operation.status = OperationStatus.FAILED.value
        operation.error = errors[0] if errors else None
    else:
        operation.status = OperationStatus.CANCELED.value
        operation.error = errors[0] if errors else None

    operation.progress = 100
    operation.completion_progress = 100
    operation.result = _aggregate_composite_results(
        result_payloads,
        succeeded=succeeded,
        failed=failed + partial,
        canceled=canceled,
        total=required_total,
    )
    summary = operation.result.get("summary") if isinstance(operation.result, dict) else None
    operation.message = str(summary or "Finished")
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
        if (
            operation is None
            or operation.status not in _ACTIVE_OPERATION_STATUSES
            or operation_cancel_requested(operation)
        ):
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
                select(TaskOperation)
                .where(TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES))
                .options(*_operation_run_graph())
            )
        )
        recoveries: list[tuple[str, str, str, int | None, str, dict[str, Any]]] = []
        for operation in operations:
            if operation_cancel_requested(operation):
                continue
            for target in operation.targets:
                if not target.recover_on_restart:
                    continue
                effective = _effective_run_for_target(target)
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
) -> list[OperationSnapshot]:
    session = get_session()
    try:
        statement = select(TaskOperation).options(*_operation_run_graph())
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
            _refresh_loaded_operation(operation)
        session.flush()
        payloads = [_operation_snapshot(operation) for operation in operations]
        session.commit()
        return payloads
    finally:
        session.close()


def get_operation(operation_id: str) -> OperationSnapshot | None:
    session = get_session()
    try:
        operation = refresh_operation(session, operation_id)
        if operation is None:
            return None
        session.flush()
        payload = _operation_snapshot(operation)
        session.commit()
        return payload
    finally:
        session.close()


def mark_operation_seen(operation_id: str) -> OperationSnapshot | None:
    session = get_session()
    try:
        operation = _load_operation_with_runs(session, operation_id)
        if operation is None:
            return None
        _refresh_loaded_operation(operation)
        operation.notification_seen_at = datetime.now(timezone.utc)
        session.flush()
        payload = _operation_snapshot(operation)
        session.commit()
        return payload
    finally:
        session.close()


def _operation_progress_meta(
        operation: TaskOperation,
        effective_runs: Sequence[TaskRun | None],
) -> dict[str, Any] | None:
    """Expose structured worker progress only when it has one unambiguous source."""
    if operation.status not in _ACTIVE_OPERATION_STATUSES:
        return None
    if operation.dependencies:
        return None
    if len(effective_runs) != 1:
        active = [run for run in effective_runs if run is not None and _task_status(run.status) not in _TERMINAL_TASK_STATUSES]
        waits = [_run_wait_state(run) for run in active]
        return {"wait_state": waits[0]} if waits and all(waits) else None
    run = effective_runs[0]
    if run is None or not isinstance(run.meta, dict):
        return None
    progress_meta = run.meta.get(TASK_RUN_PROGRESS_META_KEY)
    result = dict(progress_meta) if isinstance(progress_meta, dict) else {}
    if run_cancel_requested(run):
        result["canceling"] = True
    wait_state = _run_wait_state(run)
    if wait_state is not None:
        result["wait_state"] = wait_state
    return result or None


def _operation_snapshot(operation: TaskOperation) -> OperationSnapshot:
    targets = list(operation.targets)
    dependencies = list(operation.dependencies)
    effective_runs = [_effective_run_for_target(target) for target in targets]
    terminal_count = sum(
        run is not None and _task_status(run.status) in _TERMINAL_TASK_STATUSES
        for run in effective_runs
    ) + sum(
        dependency.child_operation is None
        or dependency.child_operation.status not in _ACTIVE_OPERATION_STATUSES
        for dependency in dependencies
    )
    return OperationSnapshot(
        id=operation.id,
        kind=operation.kind,
        source=operation.source,
        resource_type=operation.resource_type,
        resource_id=operation.resource_id,
        title=operation.title,
        status=operation.status,
        progress=operation.progress,
        completion_progress=operation.completion_progress,
        progress_current=terminal_count,
        progress_total=len(targets) + len(dependencies),
        message=operation.message,
        result=operation.result,
        context=operation.context,
        progress_meta=_operation_progress_meta(operation, effective_runs),
        error=operation.error,
        notification_seen_at=operation.notification_seen_at,
        started_at=operation.started_at,
        finished_at=operation.finished_at,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )

def _operation_run_graph():
    return (
        selectinload(TaskOperation.targets)
        .selectinload(TaskOperationTarget.run_links)
        .selectinload(TaskOperationRun.task_run),
        selectinload(TaskOperation.dependencies)
        .selectinload(TaskOperationDependency.child_operation),
    )


def _load_operation_with_runs(session: Session, operation_id: str) -> TaskOperation | None:
    return session.scalar(
        select(TaskOperation)
        .where(TaskOperation.id == operation_id)
        .options(*_operation_run_graph())
        .execution_options(populate_existing=True)
    )


def _load_target_with_runs(
        session: Session,
        operation_id: str,
        slot_key: str,
) -> TaskOperationTarget | None:
    return session.scalar(
        select(TaskOperationTarget)
        .where(
            TaskOperationTarget.operation_id == operation_id,
            TaskOperationTarget.slot_key == slot_key,
        )
        .options(
            selectinload(TaskOperationTarget.run_links).selectinload(TaskOperationRun.task_run)
        )
        .execution_options(populate_existing=True)
    )


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
        # A running worker can remain active while cooperative cancellation is
        # propagating. It cannot satisfy new work because it is guaranteed to exit.
        if run_cancel_requested(run):
            continue
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


def _run_reports_worker_progress(run: TaskRun) -> bool:
    # TaskRuns start at zero and the scheduler does not increment active progress.
    # Therefore a non-zero active percentage can only come from the worker/service
    # through ProgressUpdater and is safe to prefer over generic target completion.
    return isinstance(run.progress, int) and run.progress > 0


def _run_completion_progress(run: TaskRun) -> int:
    if _task_status(run.status) in _TERMINAL_TASK_STATUSES:
        return 100
    if isinstance(run.meta, dict):
        value = run.meta.get(TASK_RUN_COMPLETION_PROGRESS_META_KEY)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0, min(99, int(value)))
    if _run_reports_worker_progress(run):
        return max(0, min(99, int(run.progress or 0)))
    return 0


def _run_wait_state(run: TaskRun) -> dict[str, Any] | None:
    if not isinstance(run.meta, dict):
        return None
    wait_state = run.meta.get(TASK_RUN_WAIT_STATE_META_KEY)
    if not isinstance(wait_state, dict):
        return None
    reason = wait_state.get("reason")
    if not isinstance(reason, str) or not reason:
        return None
    return wait_state


def _link_target_to_run(session: Session, target: TaskOperationTarget, run: TaskRun) -> None:
    existing = session.get(TaskOperationRun, (target.id, run.id))
    if existing is not None:
        return
    session.add(TaskOperationRun(
        target=target,
        task_run=run,
        operation_id=target.operation_id,
    ))


def _latest_run_for_target(target: TaskOperationTarget) -> TaskRun | None:
    runs = [link.task_run for link in target.run_links if link.task_run is not None]
    return max(runs, key=lambda run: run.id) if runs else None


def _effective_run_for_target(target: TaskOperationTarget) -> TaskRun | None:
    """Return the run that currently determines whether a target is satisfied.

    A logical target may be linked to more than one equivalent run when automatic
    and UI work overlap. Once any linked run succeeds, the requested work is
    satisfied even if another duplicate later fails or is still running. Before
    success, the newest run represents current retry/recovery progress.
    """
    runs = [link.task_run for link in target.run_links if link.task_run is not None]
    successful = [run for run in runs if _task_status(run.status) == TaskStatus.SUCCEEDED]
    if successful:
        return max(successful, key=lambda run: run.id)
    return max(runs, key=lambda run: run.id) if runs else None


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


def _aggregate_composite_results(
        results: Sequence[dict[str, Any]],
        *,
        succeeded: int,
        failed: int,
        canceled: int,
        total: int,
) -> dict[str, Any]:
    """Aggregate orchestration outcomes without interpreting child domain data."""
    data: dict[str, Any] = {
        "completed": succeeded,
        "failed": failed,
        "canceled": canceled,
        "total": total,
    }
    summary = (
        f"Completed {total} operations"
        if not failed and not canceled
        else f"{succeeded}/{total} operations completed"
    )
    return {"summary": summary, "data": data}


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
