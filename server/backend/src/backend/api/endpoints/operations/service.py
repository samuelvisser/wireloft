from __future__ import annotations

from typing import Any

from task_manager.scheduler.operation_control import (
    cancel_operation as cancel_task_operation,
    restart_operation as restart_task_operation,
)
from task_manager.scheduler.operations import (
    get_operation as get_task_operation,
    list_operations as list_task_operations,
    mark_operation_seen as mark_task_operation_seen,
)
from task_manager.scheduler.progress import live_operation_progress_meta
from task_manager.scheduler.types import OperationStatus


_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
}


def _with_progress_meta(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_ids = [
        str(operation["id"])
        for operation in operations
        if operation.get("id")
        and operation.get("status") in _ACTIVE_OPERATION_STATUSES
        and operation.get("progress_total") == 1
    ]
    progress_meta = live_operation_progress_meta(active_ids)

    payloads: list[dict[str, Any]] = []
    for operation in operations:
        payload = dict(operation)
        operation_id = str(payload.get("id") or "")
        payload["progress_meta"] = progress_meta.get(operation_id)
        payloads.append(payload)
    return payloads


def _with_single_progress_meta(operation: dict[str, Any] | None) -> dict[str, Any] | None:
    if operation is None:
        return None
    return _with_progress_meta([operation])[0]


def list_operations(
        *,
        source: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        kind: str | None = None,
        relevant: bool = False,
        limit: int = 100,
) -> list[dict]:
    operations = list_task_operations(
        source=source,
        resource_type=resource_type,
        resource_id=resource_id,
        kind=kind,
        relevant=relevant,
        limit=limit,
    )
    return _with_progress_meta(operations)


def get_operation(operation_id: str) -> dict | None:
    return _with_single_progress_meta(get_task_operation(operation_id))


def mark_operation_seen(operation_id: str) -> dict | None:
    return _with_single_progress_meta(mark_task_operation_seen(operation_id))


def cancel_operation(operation_id: str) -> dict | None:
    return _with_single_progress_meta(cancel_task_operation(operation_id))


def restart_operation(operation_id: str) -> dict | None:
    return _with_single_progress_meta(restart_task_operation(operation_id))
