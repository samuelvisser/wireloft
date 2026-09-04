from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .TaskOperation import TaskOperation
    from .TaskOperationTarget import TaskOperationTarget
    from .TaskRun import TaskRun


# Connects logical operation targets to actual TaskRun objects.
class TaskOperationRun(Base):
    """Connects logical operation targets to actual TaskRun objects."""

    __tablename__ = "task_operation_runs"

    target_id: Mapped[int] = mapped_column(
        ForeignKey("task_operation_targets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    operation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_operations.id", ondelete="CASCADE"),
        index=True,
    )

    # Relationships
    target: Mapped["TaskOperationTarget"] = relationship(back_populates="run_links")
    task_run: Mapped["TaskRun"] = relationship(back_populates="operation_links")
    operation: Mapped["TaskOperation"] = relationship(back_populates="run_links")
