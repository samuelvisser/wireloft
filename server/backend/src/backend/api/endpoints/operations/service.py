from __future__ import annotations

from task_manager.scheduler.operation_control import (
    cancel_operation as cancel_task_operation,
    restart_operation as restart_task_operation,
)
from task_manager.scheduler.operations import (
    get_operation as get_task_operation,
    list_operations as list_task_operations,
    mark_operation_seen as mark_task_operation_seen,
)


def list_operations(
        *,
        source: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        kind: str | None = None,
        relevant: bool = False,
        limit: int = 100,
) -> list[dict]:
    return list_task_operations(
        source=source,
        resource_type=resource_type,
        resource_id=resource_id,
        kind=kind,
        relevant=relevant,
        limit=limit,
    )


def get_operation(operation_id: str) -> dict | None:
    return get_task_operation(operation_id)


def mark_operation_seen(operation_id: str) -> dict | None:
    return mark_task_operation_seen(operation_id)


def cancel_operation(operation_id: str) -> dict | None:
    return cancel_task_operation(operation_id)


def restart_operation(operation_id: str) -> dict | None:
    return restart_task_operation(operation_id)
