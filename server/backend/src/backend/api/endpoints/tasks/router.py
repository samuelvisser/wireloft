from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query

from task_manager.scheduler.types import ResourceType, TaskStatus

from ...models.tasks import (
    TaskDefinitionRead,
    TaskLedgerPageRead,
    TaskRunRead,
    TaskScheduleCreate,
    TaskScheduleRead,
)
from .service import (
    create_schedule,
    delete_schedule,
    list_definitions,
    list_ledger,
    list_runs,
    list_schedules,
    trigger_now,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/definitions", response_model=list[TaskDefinitionRead])
def definitions():
    return list_definitions()


@router.get("/schedules", response_model=list[TaskScheduleRead])
def schedules(resource_type: str | None = None, resource_id: int | None = None):
    return list_schedules(resource_type, resource_id)


@router.post("/schedules", response_model=TaskScheduleRead)
def create(body: TaskScheduleCreate):
    return create_schedule(body)


@router.delete("/schedules/{schedule_id}")
def delete(schedule_id: int):
    delete_schedule(schedule_id)
    return {"ok": True}


@router.post("/runs/trigger")
def trigger(definition_key: str, resource_type: str, resource_id: int, max_retries: int | None = None):
    return trigger_now(definition_key, resource_type, resource_id, max_retries)


@router.get("/runs", response_model=list[TaskRunRead])
def runs(
        resource_type: str | None = None,
        resource_id: int | None = None,
        status: str | None = None,
        definition_key: str | None = None,
):
    return list_runs(
        resource_type,
        resource_id,
        status,
        definition_key,
    )


@router.get("/ledger", response_model=TaskLedgerPageRead)
def ledger(
        definition_key: str,
        resource_type: ResourceType | None = None,
        resource_id: list[int] | None = Query(default=None),
        status: list[TaskStatus] | None = Query(default=None),
        started_after: datetime | None = None,
        order_by: Literal["started_at", "finished_at", "created_at"] = "started_at",
        order: Literal["asc", "desc"] = "desc",
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
):
    """Return paginated durable TaskRun history for one task type."""
    return list_ledger(
        definition_key=definition_key,
        resource_type=resource_type.value if resource_type is not None else None,
        resource_ids=resource_id,
        statuses=[item.value for item in status] if status else None,
        started_after=started_after,
        order_by=order_by,
        order=order,
        offset=offset,
        limit=limit,
    )
