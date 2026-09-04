from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .TaskOperationRun import TaskOperationRun
    from .TaskOperationTarget import TaskOperationTarget


class TaskOperation(Base):
    """A TaskOperation represents the user's high-level intent rather than an individual worker execution.

    It is usually triggered by a user action and is used to track task progress and its result when done.
    A TaskOperation can be connected to multiple TaskOperationTarget objects that represent logical units of work.
    """

    __tablename__ = "task_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(120), index=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(24), index=True)
    progress: Mapped[Optional[int]] = mapped_column(Integer)
    message: Mapped[Optional[str]] = mapped_column(Text)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    context: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)

    notification_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    targets: Mapped[list["TaskOperationTarget"]] = relationship(
        back_populates="operation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TaskOperationTarget.id",
    )
    run_links: Mapped[list["TaskOperationRun"]] = relationship(
        back_populates="operation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<TaskOperation id={self.id} kind={self.kind} status={self.status} "
            f"resource_type={self.resource_type} resource_id={self.resource_id}>"
        )
