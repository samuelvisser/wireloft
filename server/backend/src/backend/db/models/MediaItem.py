from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, func

from backend.db import Base
from backend.types import MediaType


class MediaItem(Base):
    __tablename__ = "media_items"
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": MediaType.media,
    }

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(index=True, unique=True)
    dw_id: Mapped[Optional[str]] = mapped_column(index=True, unique=True)
    type: Mapped[MediaType]
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    title: Mapped[str]
    description: Mapped[Optional[str]]
    downloaded_date: Mapped[Optional[datetime]]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    downloads: Mapped[List["MediaDownload"]] = relationship(
        back_populates="media", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MediaItem(id={self.id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"