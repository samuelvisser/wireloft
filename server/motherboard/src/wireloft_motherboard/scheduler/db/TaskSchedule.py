from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from wireloft_scheduler import TaskDefinition
from wireloft_scheduler.scheduler.types import ResourceType


class TaskSchedule(Base):
    __tablename__ = "task_schedules"

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True)
    scheduler_job_id: Mapped[Optional[str]] = mapped_column(index=True, comment="APScheduler job id")
    resource_id: Mapped[int] = mapped_column(index=True)
    resource_type: Mapped[ResourceType] = mapped_column(SAEnum(ResourceType), index=True)
    trigger: Mapped[Literal["cron", "interval", "date"]] = mapped_column(String(20))
    trigger_args: Mapped[dict] = mapped_column(JSON)
    timezone: Mapped[Optional[str]]
    next_run_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True, index=True)
    max_retries: Mapped[Optional[int]] = mapped_column(comment="Retry policy override for runs spawned by this schedule")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    definition: Mapped[TaskDefinition] = relationship()


    def __repr__(self) -> str:
        return f"<TaskSchedule id={self.id} resource_type={self.resource_type} resource_id={self.resource_id} active={self.active} created_at={self.created_at} updated_at={self.updated_at}>"