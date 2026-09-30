from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, JSON, String, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.datetime_types import UTCDateTime

if TYPE_CHECKING:
    from .TaskOperation import TaskOperation


class TaskOperationDependency(Base):
    """A durable dependency from one TaskOperation to another.

    Dependencies let a composite operation track independently meaningful child
    operations without taking over their TaskRuns. The child therefore remains
    visible and controllable through its own normal operation surfaces.
    """

    __tablename__ = "task_operation_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "parent_operation_id",
            "slot_key",
            name="uq_task_operation_dependencies_parent_slot",
        ),
        UniqueConstraint(
            "parent_operation_id",
            "child_operation_id",
            name="uq_task_operation_dependencies_parent_child",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_operation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_operations.id", ondelete="CASCADE"),
        index=True,
    )
    child_operation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("task_operations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    slot_key: Mapped[str] = mapped_column(String(255))
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    cancel_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="detach", server_default="detach")
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    parent_operation: Mapped["TaskOperation"] = relationship(
        back_populates="dependencies",
        foreign_keys=[parent_operation_id],
    )
    child_operation: Mapped["TaskOperation | None"] = relationship(
        back_populates="dependents",
        foreign_keys=[child_operation_id],
    )
