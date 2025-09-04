from __future__ import annotations

from datetime import datetime
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
    created_date: Mapped[datetime]
    modified_date: Mapped[datetime]

    # Relationships
    shows: Mapped[list["Show"]] = relationship(
        back_populates="media_profile"
    )

    def __repr__(self) -> str:
        return f"<MediaProfile(id={self.id}, name={self.name}, created_date={self.created_date}, modified_date={self.modified_date})>"