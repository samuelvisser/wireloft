from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Enum as SAEnum, ForeignKey, Index, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.datetime_types import UTCDateTime
from task_manager.scheduler.types import ResourceType, TaskStatus

if TYPE_CHECKING:
    from .TaskDefinition import TaskDefinition
    from .TaskOperationRun import TaskOperationRun


TASK_RUN_WAIT_STATE_META_KEY = "_operation_wait_state"
TASK_RUN_PROGRESS_META_KEY = "_progress_meta"
TASK_RUN_COMPLETION_PROGRESS_META_KEY = "_completion_progress"


class TaskRun(Base):
    """ A TaskRun represents one execution attempt of one registered worker """

    __tablename__ = "task_runs"
    __table_args__ = (
        Index(
            "ix_task_runs_definition_status_resource_started_id",
            "definition_id", "status", "resource_type", "resource_id", "started_at", "id",
        ),
    )

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
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())

    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    runtime_ms: Mapped[Optional[int]]

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), onupdate=func.now())

    definition: Mapped["TaskDefinition"] = relationship()

    operation_links: Mapped[list["TaskOperationRun"]] = relationship(
        back_populates="task_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def wait_state(self) -> dict[str, Any] | None:
        """Validated transient execution wait reported by the running worker.

        TaskRuns own worker execution state. TaskOperations may aggregate and
        surface this state, but they are not its source of truth.
        """
        if not isinstance(self.meta, dict):
            return None
        wait_state = self.meta.get(TASK_RUN_WAIT_STATE_META_KEY)
        if not isinstance(wait_state, dict):
            return None
        reason = wait_state.get("reason")
        if not isinstance(reason, str) or not reason:
            return None
        return wait_state

    @property
    def progress_metadata(self) -> dict[str, Any] | None:
        """Structured live progress emitted by the worker, when present."""
        if not isinstance(self.meta, dict):
            return None
        progress_meta = self.meta.get(TASK_RUN_PROGRESS_META_KEY)
        return progress_meta if isinstance(progress_meta, dict) else None

    @property
    def reported_completion_progress(self) -> int | None:
        """Worker-reported completion percentage used by aggregate operations."""
        if not isinstance(self.meta, dict):
            return None
        value = self.meta.get(TASK_RUN_COMPLETION_PROGRESS_META_KEY)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return max(0, min(99, int(value)))

    def __repr__(self) -> str:
        return f"<TaskRun id={self.id} resource_type={self.resource_type} resource_id={self.resource_id} status={self.status} progress={self.progress} created_at={self.created_at} updated_at={self.updated_at}>"
