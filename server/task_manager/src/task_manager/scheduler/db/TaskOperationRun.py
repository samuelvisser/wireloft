from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class TaskOperationRun(Base):
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
