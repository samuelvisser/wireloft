from __future__ import annotations

from datetime import datetime
from hashlib import blake2b
from typing import Literal, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from backend.api.pagination import InvalidCursorError, decode_cursor, encode_cursor
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


def _task_ledger_cursor_filter(
    order_column,
    *,
    value: datetime | None,
    run_id: int,
    descending: bool,
):
    if value is None:
        return and_(
            order_column.is_(None),
            TaskRun.id < run_id if descending else TaskRun.id > run_id,
        )

    value_comparison = order_column < value if descending else order_column > value
    id_comparison = TaskRun.id < run_id if descending else TaskRun.id > run_id
    return or_(
        value_comparison,
        and_(order_column == value, id_comparison),
        order_column.is_(None),
    )


def _task_ledger_collection_revision(
    session: Session,
    *,
    filters: list,
    definition_key: str | None,
    ordering,
    tie_breaker,
) -> tuple[str, int]:
    """Fingerprint only the ordered task IDs matching these filters.

    Progress and other changes to a TaskRun do not invalidate a cursor unless
    they change its membership or its position in this particular collection.
    The ordered ID stream also provides the exact total without a second count
    query, and does not hydrate task objects into memory.
    """
    statement = select(TaskRun.id).where(*filters)
    if definition_key is not None:
        statement = statement.join(
            TaskDefinition,
            TaskDefinition.id == TaskRun.definition_id,
        )
    digest = blake2b(digest_size=16)
    total = 0
    for run_id in session.scalars(
        statement.order_by(ordering, tie_breaker)
    ).yield_per(512):
        digest.update(f"{run_id},".encode("ascii"))
        total += 1
    return digest.hexdigest(), total


def query_ledger(
    s: Session,
    *,
    definition_key: str | None,
    resource_type: str | None = None,
    resource_ids: list[int] | None = None,
    statuses: list[str] | None = None,
    started_after: datetime | None = None,
    order_by: Literal["started_at", "finished_at", "created_at"] = "started_at",
    order: Literal["asc", "desc"] = "desc",
    cursor: str | None = None,
    limit: int = 50,
) -> TaskLedgerPageRead:
    """Query cursor-paginated TaskRun history using a caller-owned database session."""
    filters = []
    if definition_key is not None:
        filters.append(TaskDefinition.key == definition_key)
    if resource_type is not None:
        filters.append(TaskRun.resource_type == ResourceType(resource_type))
    if resource_ids:
        filters.append(TaskRun.resource_id.in_(resource_ids))
    if statuses:
        filters.append(TaskRun.status.in_([TaskStatus(status) for status in statuses]))
    if started_after is not None:
        filters.append(TaskRun.started_at >= started_after)

    cursor_scope = {
        "definition_key": definition_key,
        "resource_type": resource_type,
        "resource_ids": sorted(resource_ids or []),
        "statuses": sorted(statuses or []),
        "started_after": started_after.isoformat() if started_after is not None else None,
    }

    order_column = {
        "started_at": TaskRun.started_at,
        "finished_at": TaskRun.finished_at,
        "created_at": TaskRun.created_at,
    }[order_by]
    descending = order == "desc"
    ordering = (
        order_column.desc().nulls_last()
        if descending
        else order_column.asc().nulls_last()
    )
    tie_breaker = TaskRun.id.desc() if descending else TaskRun.id.asc()

    revision, total = _task_ledger_collection_revision(
        s,
        filters=filters,
        definition_key=definition_key,
        ordering=ordering,
        tie_breaker=tie_breaker,
    )

    if cursor:
        try:
            values = decode_cursor(cursor)
            if (
                values.get("kind") != "task-ledger"
                or values.get("order_by") != order_by
                or values.get("order") != order
                or values.get("scope") != cursor_scope
            ):
                raise InvalidCursorError("Cursor does not match this task ledger")
            cursor_id = values.get("id")
            if not isinstance(cursor_id, int) or isinstance(cursor_id, bool):
                raise InvalidCursorError("Invalid task ledger cursor id")
            if values.get("revision") == revision:
                # Resolve the cursor row's current sort key to avoid skips when its
                # timestamp moves without changing its relative rank.
                anchor_stmt = select(order_column).where(TaskRun.id == cursor_id, *filters)
                if definition_key is not None:
                    anchor_stmt = anchor_stmt.join(
                        TaskDefinition,
                        TaskDefinition.id == TaskRun.definition_id,
                    )
                anchor = s.execute(anchor_stmt).first()
                if anchor is None:
                    raise InvalidCursorError("Invalid task ledger cursor id")
                filters.append(_task_ledger_cursor_filter(
                    order_column,
                    value=anchor[0],
                    run_id=cursor_id,
                    descending=descending,
                ))
            # Otherwise restart at the first page. The shared lazy collection
            # reconciles mismatched page revisions using the authoritative head.
        except (InvalidCursorError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    run_stmt = (
        select(TaskRun)
        .options(joinedload(TaskRun.definition))
        .where(*filters)
    )
    if definition_key is not None:
        run_stmt = run_stmt.join(
            TaskDefinition,
            TaskDefinition.id == TaskRun.definition_id,
        )

    runs = list(s.scalars(
        run_stmt
        .order_by(ordering, tie_breaker)
        .limit(limit + 1)
    ).all())
    has_more = len(runs) > limit
    runs = runs[:limit]

    next_cursor = None
    if has_more and runs:
        last = runs[-1]
        next_cursor = encode_cursor({
            "kind": "task-ledger",
            "order_by": order_by,
            "order": order,
            "scope": cursor_scope,
            "revision": revision,
            "id": last.id,
        })

    items = [TaskLedgerEntryRead.model_validate(run) for run in runs]
    return TaskLedgerPageRead(
        items=items,
        total=total,
        limit=limit,
        next_cursor=next_cursor,
        revision=revision,
    )


def list_ledger(
    *,
    definition_key: str | None,
    resource_type: str | None = None,
    resource_ids: list[int] | None = None,
    statuses: list[str] | None = None,
    started_after: datetime | None = None,
    order_by: Literal["started_at", "finished_at", "created_at"] = "started_at",
    order: Literal["asc", "desc"] = "desc",
    cursor: str | None = None,
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
            cursor=cursor,
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
