from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.api.models.tasks import (
    TaskDefinitionRead,
    TaskLedgerEntryRead,
    TaskLedgerPageRead,
    TaskRunRead,
    TaskScheduleCreate,
    TaskScheduleRead,
    TaskTriggerRead,
)
from backend.db.core import get_session
from task_manager.scheduler.db import TaskDefinition, TaskRun, TaskSchedule
from task_manager.scheduler.executor import trigger_now as exec_trigger_now
from task_manager.scheduler.scheduler import remove_job, schedule_job
from task_manager.scheduler.types import ResourceType, TaskStatus


def list_definitions() -> list[TaskDefinitionRead]:
    s = get_session()
    try:
        return [
            TaskDefinitionRead.model_validate(item)
            for item in s.scalars(select(TaskDefinition)).all()
        ]
    finally:
        s.close()


def create_schedule(body: TaskScheduleCreate) -> TaskScheduleRead:
    s = get_session()
    try:
        definition = s.scalar(
            select(TaskDefinition).where(TaskDefinition.key == body.definition_key)
        )
        if definition is None:
            raise ValueError(f"Unknown task definition {body.definition_key!r}")

        schedule = TaskSchedule(
            definition=definition,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            trigger=body.trigger,
            trigger_args=body.trigger_args,
            active=True,
            max_retries=body.max_retries,
        )
        s.add(schedule)
        s.flush()
        schedule.scheduler_job_id = schedule_job(
            schedule_id=schedule.id,
            def_key=definition.key,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            trigger=body.trigger,
            trigger_args=body.trigger_args,
        )
        payload = TaskScheduleRead.model_validate(schedule)
        s.commit()
        return payload
    finally:
        s.close()


def delete_schedule(schedule_id: int) -> None:
    s = get_session()
    try:
        schedule = s.get(TaskSchedule, schedule_id)
        if schedule is None:
            return
        remove_job(schedule_id)
        s.delete(schedule)
        s.commit()
    finally:
        s.close()


def list_schedules(
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
) -> list[TaskScheduleRead]:
    s = get_session()
    try:
        stmt = select(TaskSchedule).options(joinedload(TaskSchedule.definition))
        if resource_type is not None:
            stmt = stmt.where(TaskSchedule.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(TaskSchedule.resource_id == resource_id)
        return [
            TaskScheduleRead.model_validate(item)
            for item in s.scalars(stmt).all()
        ]
    finally:
        s.close()


def list_runs(
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    status: Optional[str] = None,
    definition_key: str | None = None,
) -> list[TaskRunRead]:
    s = get_session()
    try:
        stmt = (
            select(TaskRun)
            .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
            .options(joinedload(TaskRun.definition))
            .order_by(TaskRun.started_at.desc())
        )
        if resource_type is not None:
            stmt = stmt.where(TaskRun.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(TaskRun.resource_id == resource_id)
        if status is not None:
            stmt = stmt.where(TaskRun.status == status)
        if definition_key is not None:
            stmt = stmt.where(TaskDefinition.key == definition_key)
        return [TaskRunRead.model_validate(run) for run in s.scalars(stmt).all()]
    finally:
        s.close()


def query_ledger(
    s: Session,
    *,
    definition_key: str,
    resource_type: str | None = None,
    resource_ids: list[int] | None = None,
    statuses: list[str] | None = None,
    started_after: datetime | None = None,
    order_by: Literal["started_at", "finished_at", "created_at"] = "started_at",
    order: Literal["asc", "desc"] = "desc",
    offset: int = 0,
    limit: int = 50,
) -> TaskLedgerPageRead:
    """Query paginated TaskRun history using a caller-owned database session."""
    filters = [TaskDefinition.key == definition_key]
    if resource_type is not None:
        filters.append(TaskRun.resource_type == ResourceType(resource_type))
    if resource_ids:
        filters.append(TaskRun.resource_id.in_(resource_ids))
    if statuses:
        filters.append(TaskRun.status.in_([TaskStatus(status) for status in statuses]))
    if started_after is not None:
        filters.append(TaskRun.started_at >= started_after)

    total = int(
        s.execute(
            select(func.count(TaskRun.id))
            .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
            .where(*filters)
        ).scalar_one()
    )

    order_column = {
        "started_at": TaskRun.started_at,
        "finished_at": TaskRun.finished_at,
        "created_at": TaskRun.created_at,
    }[order_by]
    ordering = order_column.asc() if order == "asc" else order_column.desc()
    tie_breaker = TaskRun.id.asc() if order == "asc" else TaskRun.id.desc()

    runs = s.scalars(
        select(TaskRun)
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .options(joinedload(TaskRun.definition))
        .where(*filters)
        .order_by(ordering, tie_breaker)
        .offset(offset)
        .limit(limit)
    ).all()

    items = [TaskLedgerEntryRead.model_validate(run) for run in runs]
    return TaskLedgerPageRead(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + len(items) < total,
    )


def list_ledger(
    *,
    definition_key: str,
    resource_type: str | None = None,
    resource_ids: list[int] | None = None,
    statuses: list[str] | None = None,
    started_after: datetime | None = None,
    order_by: Literal["started_at", "finished_at", "created_at"] = "started_at",
    order: Literal["asc", "desc"] = "desc",
    offset: int = 0,
    limit: int = 50,
) -> TaskLedgerPageRead:
    s = get_session()
    try:
        return query_ledger(
            s,
            definition_key=definition_key,
            resource_type=resource_type,
            resource_ids=resource_ids,
            statuses=statuses,
            started_after=started_after,
            order_by=order_by,
            order=order,
            offset=offset,
            limit=limit,
        )
    finally:
        s.close()


def trigger_now(
    definition_key: str,
    resource_type: str,
    resource_id: Optional[int],
    max_retries: Optional[int] = None,
    **kwargs,
) -> TaskTriggerRead:
    return TaskTriggerRead(
        job_id=exec_trigger_now(
            def_key=definition_key,
            resource_type=resource_type,
            resource_id=resource_id,
            max_retries=max_retries,
            **kwargs,
        )
    )
