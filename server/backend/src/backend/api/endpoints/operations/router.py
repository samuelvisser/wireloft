from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.models.operations import TaskOperationRead
from .service import get_operation, list_operations, mark_operation_seen


router = APIRouter(prefix="/operations", tags=["Operations"])


@router.get("", response_model=list[TaskOperationRead])
def operations(
        source: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        kind: str | None = None,
        relevant: bool = False,
        limit: int = 100,
):
    """List durable high-level task operations, optionally filtered by resource."""
    return list_operations(
        source=source,
        resource_type=resource_type,
        resource_id=resource_id,
        kind=kind,
        relevant=relevant,
        limit=limit,
    )


@router.get("/{operation_id}", response_model=TaskOperationRead)
def operation(operation_id: str):
    result = get_operation(operation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Operation not found")
    return result


@router.post("/{operation_id}/seen", response_model=TaskOperationRead)
def operation_seen(operation_id: str):
    """Acknowledge a terminal UI operation after its notification was presented."""
    result = mark_operation_seen(operation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Operation not found")
    return result
