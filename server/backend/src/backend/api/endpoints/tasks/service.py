from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from backend.db.core import get_session
from wireloft_scheduler.models import TaskDefinition, TaskSchedule, TaskRun
from wireloft_scheduler.scheduler import schedule_job, remove_job
from wireloft_scheduler.executor import trigger_now as exec_trigger_now


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


def list_runs(resource_type: Optional[str] = None, resource_id: Optional[int] = None, status: Optional[str] = None) -> list[dict]:
    s = get_session()
    try:
        stmt = select(TaskRun, TaskDefinition.key).join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        if resource_type is not None:
            stmt = stmt.where(TaskRun.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(TaskRun.resource_id == resource_id)
        if status is not None:
            stmt = stmt.where(TaskRun.status == status)
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


def trigger_now(definition_key: str, resource_type: str, resource_id: int, max_retries: Optional[int] = None) -> dict:
    job_id = exec_trigger_now(def_key=definition_key, resource_type=resource_type, resource_id=resource_id, max_retries=max_retries)
    return {"jobId": job_id}
