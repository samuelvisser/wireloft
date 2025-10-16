from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime, func, UniqueConstraint

from backend.db import Base
from backend.types.media_types import MediaType

if TYPE_CHECKING:
    from backend.db.models.media_download import MediaDownloadBase


class MediaItemBase(Base):
    __tablename__ = "media_items"
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": MediaType.BASE.value,
    }
    __table_args__ = (
        UniqueConstraint("type", "slug", name="uq_unique_slug_per_media_type"),
        UniqueConstraint("type", "dw_id", name="uq_unique_dw_id_per_media_type"),
    )

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(index=True, unique=True)
    dw_id: Mapped[Optional[str]] = mapped_column(index=True)
    type: Mapped[str]
    slug: Mapped[str]
    title: Mapped[str]
    description: Mapped[Optional[str]]
    downloaded_date: Mapped[Optional[datetime]]

    duration: Mapped[float]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    downloads: Mapped[List["MediaDownloadBase"]] = relationship(
        back_populates="media", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MediaItem(id={self.id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"