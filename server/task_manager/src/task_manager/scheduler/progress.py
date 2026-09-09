from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from backend.db.core import get_session
from task_manager.scheduler.db import TaskOperationRun, TaskRun
from task_manager.scheduler.types import TaskStatus


TASK_RUN_PROGRESS_META_KEY = "_progress_meta"
_ACTIVE_TASK_STATUSES = (
    TaskStatus.SCHEDULED,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.RETRY_SCHEDULED,
)


def task_run_progress_meta(meta: object) -> dict[str, Any] | None:
    """Return worker-reported live metadata from a TaskRun metadata payload."""
    if not isinstance(meta, dict):
        return None
    progress_meta = meta.get(TASK_RUN_PROGRESS_META_KEY)
    return dict(progress_meta) if isinstance(progress_meta, dict) else None


def live_operation_progress_meta(operation_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Return unambiguous live worker metadata for active single-run operations.

    TaskOperation keeps durable operation identity and aggregate state while the
    linked TaskRun owns worker progress. API callers can use this helper to expose
    details reported through ``ProgressUpdater`` without copying them into an
    operation context or domain model.

    Multi-run operations deliberately return no metadata because there is no
    generic way to merge arbitrary worker-specific values across targets.
    """
    ids = tuple(dict.fromkeys(str(operation_id) for operation_id in operation_ids if operation_id))
    if not ids:
        return {}

    session = get_session()
    try:
        rows = session.execute(
            select(
                TaskOperationRun.operation_id,
                TaskRun.id,
                TaskRun.meta,
            )
            .select_from(TaskOperationRun)
            .join(TaskRun, TaskRun.id == TaskOperationRun.task_run_id)
            .where(
                TaskOperationRun.operation_id.in_(ids),
                TaskRun.status.in_(_ACTIVE_TASK_STATUSES),
            )
            .order_by(TaskOperationRun.operation_id, TaskRun.id.desc())
        ).all()
    finally:
        session.close()

    runs_by_operation: dict[str, dict[int, dict[str, Any] | None]] = {}
    for operation_id, run_id, meta in rows:
        runs_by_operation.setdefault(operation_id, {})[run_id] = task_run_progress_meta(meta)

    result: dict[str, dict[str, Any]] = {}
    for operation_id, runs in runs_by_operation.items():
        if len(runs) != 1:
            continue
        progress_meta = next(iter(runs.values()))
        if progress_meta:
            result[operation_id] = progress_meta
    return result
