from __future__ import annotations

from fastapi import APIRouter, Query

from ...models.tasks import TaskDefinitionRead, TaskScheduleCreate, TaskScheduleRead, TaskRunRead
from .service import list_definitions, list_schedules, create_schedule, delete_schedule, list_runs, trigger_now

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
def runs(resource_type: str | None = None, resource_id: int | None = None, status: str | None = None):
    return list_runs(resource_type, resource_id, status)
