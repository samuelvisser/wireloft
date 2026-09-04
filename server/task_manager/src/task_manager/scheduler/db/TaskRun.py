from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from task_manager.scheduler.types import ResourceType, TaskStatus

if TYPE_CHECKING:
    from .TaskOperationRun import TaskOperationRun


class TaskRun(Base):
    """ A TaskRun represents one execution attempt of one registered worker """


    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task_schedules.id", ondelete="SET NULL"), index=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True)

    resource_type: Mapped[ResourceType] = mapped_column(SAEnum(ResourceType), index=True)
    resource_id: Mapped[Optional[int]] = mapped_column(index=True)

    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), index=True)
    progress: Mapped[Optional[int]]
    message: Mapped[Optional[str]]
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[Optional[str]]
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    runtime_ms: Mapped[Optional[int]]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    operation_links: Mapped[list["TaskOperationRun"]] = relationship(
        back_populates="task_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<TaskRun id={self.id} resource_type={self.resource_type} resource_id={self.resource_id} status={self.status} progress={self.progress} created_at={self.created_at} updated_at={self.updated_at}>"
