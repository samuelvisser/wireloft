from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.types.download_profile_types import DownloadProfileType

class DownloadProfileBase(Base):
    __tablename__ = "download_profiles"
    __table_args__ = (
        UniqueConstraint("show_id", "media_profile_id", name="uq_unique_media_profile_per_show"),
    )
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": DownloadProfileType.base,
    }

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))
    media_profile_id: Mapped[int] = mapped_column(ForeignKey("media_profiles.id"))
    type: Mapped[DownloadProfileType]
    enable_profile: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="download_profiles")
    media_profile: Mapped["MediaProfile"] = relationship(back_populates="download_profiles")


    def __repr__(self) -> str:
        return f"<DownloadProfileBase(id={self.id}, show_id={self.show_id}, enable_profile={self.enable_profile}, created_at={self.created_at}, updated_at={self.updated_at})>"