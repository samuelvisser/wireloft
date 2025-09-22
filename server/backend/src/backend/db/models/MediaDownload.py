from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime, func
from sqlalchemy.sql.schema import ForeignKey

from backend.db import Base
from backend.types.download_profile_types import MediaDownloadStatus


class MediaDownload(Base):
    __tablename__ = "media_downloads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
    media: Mapped["MediaItem"] = relationship(back_populates="downloads")


    def __repr__(self) -> str:
        return f"<MediaDownload(id={self.id}, download_status={self.download_status}, file_path={self.file_path}, created_at={self.created_at}, updated_at={self.updated_at})>"