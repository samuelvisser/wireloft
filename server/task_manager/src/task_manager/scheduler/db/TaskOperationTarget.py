from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .TaskOperation import TaskOperation
    from .TaskOperationRun import TaskOperationRun



class TaskOperationTarget(Base):
    """ Represents the logical units of work that must be fulfilled for an operation.

    Usually used by a TaskOperation to trigger one or more tasks (workers) to finish the operation.
    """

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

    # Relationships
    operation: Mapped["TaskOperation"] = relationship(back_populates="targets")
    run_links: Mapped[list["TaskOperationRun"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TaskOperationRun.task_run_id",
    )
