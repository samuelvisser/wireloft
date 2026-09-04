from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


# Represents the logical units of work that must be fulfilled for an operation
# Usually used by a TaskOperation to trigger single or multiple tasks (workers) to finish the operation.
class TaskOperationTarget(Base):
    __tablename__ = "task_operation_targets"
    __table_args__ = (
        UniqueConstraint("operation_id", "slot_key", name="uq_task_operation_targets_operation_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_operations.id", ondelete="CASCADE"),
        index=True,
    )
    task_key: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, index=True)
    slot_key: Mapped[str] = mapped_column(String(255))
    task_kwargs: Mapped[dict | None] = mapped_column(JSON)
    recover_on_restart: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
