from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base

class MediaProfile(Base):
    __tablename__ = "media_profiles"

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    name: Mapped[str]
    output_template: Mapped[str]
    preferred_format: Mapped[str]
    download_series_images: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    download_profiles: Mapped[list["DownloadProfileBase"]] = relationship(back_populates="media_profile")


    def __repr__(self) -> str:
        return f"<MediaProfile(id={self.id}, slug={self.slug}, name={self.name}, created_at={self.created_at}, updated_at={self.updated_at})>"