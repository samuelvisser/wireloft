from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .MediaDownloadBase import MediaDownloadBase


class MediaDownloadAttempt(Base):
    """Legacy download-history rows retained for schema/data compatibility.

    WireLoft no longer writes or serves this table. TaskRun is the canonical
    execution ledger; keeping the mapped table avoids a destructive migration
    that would erase pre-existing attempt history during this change.
    """
    __tablename__ = "media_download_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    media_download_id: Mapped[int] = mapped_column(ForeignKey("media_downloads.id", ondelete="CASCADE"), index=True)
    is_redownload: Mapped[bool]
    status: Mapped[str]
    error_message: Mapped[Optional[str]]
    downloaded_bytes: Mapped[Optional[int]]
    format_downloaded: Mapped[Optional[str]]
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    media_download: Mapped["MediaDownloadBase"] = relationship(back_populates="attempts")

    def __repr__(self) -> str:
        return f"<MediaDownloadAttempt(id={self.id}, media_download_id={self.media_download_id}, status={self.status}, created_at={self.created_at})>"
