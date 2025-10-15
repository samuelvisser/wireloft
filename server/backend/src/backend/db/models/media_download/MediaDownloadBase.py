from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime, func
from sqlalchemy.sql.schema import ForeignKey

from backend.db import Base
from backend.types.media_types import MediaType

if TYPE_CHECKING:
    from backend.db.models.media_item import MediaItemBase


class MediaDownloadBase(Base):
    __tablename__ = "media_downloads"
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": MediaType.BASE.value,
    }

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]
    media_item_id: Mapped[int] = mapped_column(ForeignKey("media_items.id"))
    download_status: Mapped[str]
    file_path: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    media: Mapped["MediaItemBase"] = relationship(back_populates="downloads")


    def __repr__(self) -> str:
        return f"<MediaDownload(id={self.id}, download_status={self.download_status}, file_path={self.file_path}, created_at={self.created_at}, updated_at={self.updated_at})>"