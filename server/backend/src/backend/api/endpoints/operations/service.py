from __future__ import annotations

from backend.api.models.operations import TaskOperationRead
from task_manager.scheduler.operation_control import (
    cancel_operation as cancel_task_operation,
    restart_operation as restart_task_operation,
)
from task_manager.tasks.media_download_operations import (
    MEDIA_DOWNLOAD_OPERATION_KIND,
    cancel_media_download_operation,
    restart_media_download_operation,
)
from task_manager.scheduler.operations import (
    get_operation as get_task_operation,
    list_operations as list_task_operations,
    mark_operation_seen as mark_task_operation_seen,
)


def _read(snapshot) -> TaskOperationRead | None:
    return TaskOperationRead.model_validate(snapshot) if snapshot is not None else None


def list_operations(
        *,
        source: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        kind: str | None = None,
        relevant: bool = False,
        limit: int = 100,
) -> list[TaskOperationRead]:
    return [
        TaskOperationRead.model_validate(snapshot)
        for snapshot in list_task_operations(
            source=source,
            resource_type=resource_type,
            resource_id=resource_id,
            kind=kind,
            relevant=relevant,
            limit=limit,
        )
    ]


def get_operation(operation_id: str) -> TaskOperationRead | None:
    return _read(get_task_operation(operation_id))


def mark_operation_seen(operation_id: str) -> TaskOperationRead | None:
    return _read(mark_task_operation_seen(operation_id))


def cancel_operation(operation_id: str) -> TaskOperationRead | None:
    operation = get_task_operation(operation_id)
    if operation is not None and operation.kind == MEDIA_DOWNLOAD_OPERATION_KIND:
        return _read(cancel_media_download_operation(operation_id))
    return _read(cancel_task_operation(operation_id))


def restart_operation(operation_id: str) -> TaskOperationRead | None:
    operation = get_task_operation(operation_id)
    if operation is not None and operation.kind == MEDIA_DOWNLOAD_OPERATION_KIND:
        return _read(restart_media_download_operation(operation_id))
    return _read(restart_task_operation(operation_id))
