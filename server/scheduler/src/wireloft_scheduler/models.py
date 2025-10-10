from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Literal

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, JSON, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class TaskStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"


class ResourceType(str, Enum):
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"
    MOVIE = "movie"


class TaskDefinition(Base):
    __tablename__ = "task_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]]
    allowed_resource_types: Mapped[Optional[list[str]]] = mapped_column(JSON)
    # default max retries if not provided by schedule or trigger_now
    default_max_retries: Mapped[Optional[int]] = mapped_column(Integer)


class TaskSchedule(Base):
    __tablename__ = "task_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True)
    definition: Mapped[TaskDefinition] = relationship()

    resource_type: Mapped[ResourceType] = mapped_column(SAEnum(ResourceType), index=True)
    resource_id: Mapped[int] = mapped_column(index=True)

    trigger: Mapped[Literal["cron", "interval", "date"]] = mapped_column(String(20))
    trigger_args: Mapped[dict] = mapped_column(JSON)

    timezone: Mapped[Optional[str]]
    next_run_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True, index=True)

    # APS job id
    scheduler_job_id: Mapped[Optional[str]] = mapped_column(index=True)

    # retry policy override for runs spawned by this schedule
    max_retries: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task_schedules.id", ondelete="SET NULL"), index=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True)

    resource_type: Mapped[ResourceType] = mapped_column(SAEnum(ResourceType), index=True)
    resource_id: Mapped[int] = mapped_column(index=True)

    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), index=True)
    progress: Mapped[Optional[int]] = mapped_column(Integer)
    message: Mapped[Optional[str]]
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]]
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    runtime_ms: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
