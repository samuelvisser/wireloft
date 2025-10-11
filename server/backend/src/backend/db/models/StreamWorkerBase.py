from datetime import datetime

from sqlalchemy import DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.types.stream_worker_types import StreamWorkerType


class StreamWorkerBase(Base):
    __tablename__ = "stream_workers"
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": StreamWorkerType.BASE.value,
    }

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]
    stream_profile_id: Mapped[int] = mapped_column(ForeignKey("stream_profiles.id"), unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    stream_profile: Mapped["StreamProfileBase"] = relationship(back_populates="stream_worker", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<StreamWorkerBase(id={self.id}, type={self.type}, stream_profile_id={self.stream_profile_id}, created_at={self.created_at}, updated_at={self.updated_at})>"