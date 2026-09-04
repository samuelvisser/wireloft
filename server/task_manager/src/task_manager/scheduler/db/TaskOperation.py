from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class TaskOperation(Base):
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

    def __repr__(self) -> str:
        return (
            f"<TaskOperation id={self.id} kind={self.kind} status={self.status} "
            f"resource_type={self.resource_type} resource_id={self.resource_id}>"
        )
