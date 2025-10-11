from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.types.stream_profile_types import StreamProfileType

class StreamProfileBase(Base):
    __tablename__ = "stream_profiles"
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": StreamProfileType.BASE.value,
    }

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]
    enable_profile: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    stream_worker: Mapped["StreamWorkerBase"] = relationship(
        back_populates="stream_profile", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<StreamProfileBase(id={self.id}, enable_profile={self.enable_profile}, created_at={self.created_at}, updated_at={self.updated_at})>"