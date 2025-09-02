from __future__ import annotations

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.db.models.Show import Show

class MediaProfile(Base):
    __tablename__ = "media_profiles"

    # Columns
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    output_template: Mapped[str]
    preferred_format: Mapped[str]
    download_series_images: Mapped[bool]
    created_date: Mapped[DateTime]
    modified_date: Mapped[DateTime]

    # Relationships
    shows: Mapped[list["Show"]] = relationship(
        back_populates="media_profile"
    )

    def __repr__(self) -> str:
        return f"<MediaProfile(id={self.id}, name={self.name}, created_date={self.created_date}, modified_date={self.modified_date})>"