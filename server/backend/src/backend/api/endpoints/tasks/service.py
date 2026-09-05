from __future__ import annotations

from typing import Literal, Optional

from sqlalchemy import func, select

from backend.db.core import get_session
from task_manager.scheduler.db import TaskDefinition, TaskSchedule, TaskRun
from task_manager.scheduler.scheduler import schedule_job, remove_job
from task_manager.scheduler.executor import trigger_now as exec_trigger_now
from task_manager.scheduler.types import ResourceType


def list_definitions() -> list[dict]:
    s = get_session()
    try:
        rows = s.execute(select(TaskDefinition)).scalars().all()
        return [
            {
                "id": r.id,
                "key": r.key,
                "title": r.title,
                "description": r.description,
                "allowed_resource_types": r.allowed_resource_types,
                "default_max_retries": r.default_max_retries,
            }
            for r in rows
        ]
    finally:
        s.close()


def create_schedule(body) -> dict:
    s = get_session()
    try:
        td = s.execute(select(TaskDefinition).where(TaskDefinition.key == body.definition_key)).scalar_one()
        sch = TaskSchedule(
            definition_id=td.id,
            resource_type=body.resource_type,  # Enum validated by Pydantic layer
            resource_id=body.resource_id,
            trigger=body.trigger,
            trigger_args=body.trigger_args,
            timezone=None,
            active=True,
            max_retries=body.max_retries,
        )
        s.add(sch)
        s.flush()
        # schedule with APS
        job_id = schedule_job(
            schedule_id=sch.id,
            def_key=td.key,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            trigger=body.trigger,
            trigger_args=body.trigger_args,
        )
        sch.scheduler_job_id = job_id
        s.commit()
        return _schedule_to_dict(sch, td.key)
    finally:
        s.close()


def delete_schedule(schedule_id: int) -> None:
    s = get_session()
    try:
        sch = s.get(TaskSchedule, schedule_id)
        if sch is None:
            return
        remove_job(schedule_id)
        s.delete(sch)
        s.commit()
    finally:
        s.close()


def list_schedules(resource_type: Optional[str] = None, resource_id: Optional[int] = None) -> list[dict]:
    s = get_session()
    try:
        stmt = select(TaskSchedule, TaskDefinition.key).join(TaskDefinition, TaskDefinition.id == TaskSchedule.definition_id)
        if resource_type is not None:
            stmt = stmt.where(TaskSchedule.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(TaskSchedule.resource_id == resource_id)
        rows = s.execute(stmt).all()
        return [_schedule_to_dict(sch, def_key) for sch, def_key in rows]
    finally:
        s.close()


def _schedule_to_dict(sch: TaskSchedule, def_key: str) -> dict:
    return {
        "id": sch.id,
        "definition_key": def_key,
        "resource_type": sch.resource_type.value if hasattr(sch.resource_type, "value") else sch.resource_type,
        "resource_id": sch.resource_id,
        "trigger": sch.trigger,
        "trigger_args": sch.trigger_args,
        "active": sch.active,
        "next_run_time": sch.next_run_time.isoformat() if sch.next_run_time else None,
        "max_retries": sch.max_retries,
    }


def list_runs(
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        status: Optional[str] = None,
        definition_key: str | None = None,
) -> list[dict]:
    s = get_session()
    try:
        stmt = select(TaskRun, TaskDefinition.key).join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id).order_by(TaskRun.started_at.desc())
        if resource_type is not None:
            stmt = stmt.where(TaskRun.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(TaskRun.resource_id == resource_id)
        if status is not None:
            stmt = stmt.where(TaskRun.status == status)
        if definition_key is not None:
            stmt = stmt.where(TaskDefinition.key == definition_key)

        rows = s.execute(stmt).all()
        return [
            {
                "id": r.id,
                "definition_key": def_key,
                "resource_type": r.resource_type.value if hasattr(r.resource_type, "value") else r.resource_type,
                "resource_id": r.resource_id,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "progress": r.progress,
                "message": r.message,
                "result": r.result,
                "attempt_count": r.attempt_count,
                "max_retries": r.max_retries,
                "last_error": r.last_error,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "runtime_ms": r.runtime_ms,
            }
            for r, def_key in rows
        ]
    finally:
        s.close()


def list_ledger(
        *,
        definition_key: str,
        resource_type: str | None = None,
        resource_id: int | None = None,
        order_by: Literal["started_at", "finished_at", "created_at"] = "started_at",
        order: Literal["asc", "desc"] = "desc",
        offset: int = 0,
        limit: int = 50,
) -> dict:
    """Return paginated TaskRun history without worker-specific presentation data."""
    s = get_session()
    try:
        filters = [TaskDefinition.key == definition_key]
        if resource_type is not None:
            filters.append(TaskRun.resource_type == ResourceType(resource_type))
        if resource_id is not None:
            filters.append(TaskRun.resource_id == resource_id)

        total = int(s.execute(
            select(func.count(TaskRun.id))
            .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
            .where(*filters)
        ).scalar_one())

        order_column = {
            "started_at": TaskRun.started_at,
            "finished_at": TaskRun.finished_at,
            "created_at": TaskRun.created_at,
        }[order_by]
        ordering = order_column.asc() if order == "asc" else order_column.desc()
        tie_breaker = TaskRun.id.asc() if order == "asc" else TaskRun.id.desc()

        rows = s.execute(
            select(TaskRun, TaskDefinition.key)
            .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
            .where(*filters)
            .order_by(ordering, tie_breaker)
            .offset(offset)
            .limit(limit)
        ).all()

        items = []
        for run, def_key in rows:
            meta = run.meta if isinstance(run.meta, dict) else {}
            inputs = meta.get("inputs") if isinstance(meta.get("inputs"), dict) else {}
            items.append({
                "id": run.id,
                "definition_key": def_key,
                "resource_type": run.resource_type.value if hasattr(run.resource_type, "value") else run.resource_type,
                "resource_id": run.resource_id,
                "status": run.status.value if hasattr(run.status, "value") else run.status,
                "message": run.message,
                "last_error": run.last_error,
                "inputs": inputs,
                "result": run.result,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "runtime_ms": run.runtime_ms,
            })

        return {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < total,
        }
    finally:
        s.close()


def trigger_now(definition_key: str, resource_type: str, resource_id: Optional[int], max_retries: Optional[int] = None, **kwargs) -> dict:
    job_id = exec_trigger_now(def_key=definition_key, resource_type=resource_type, resource_id=resource_id, max_retries=max_retries, **kwargs)
    return {"jobId": job_id}
