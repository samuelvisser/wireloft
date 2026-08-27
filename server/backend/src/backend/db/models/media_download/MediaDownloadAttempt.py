from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .MediaDownloadBase import MediaDownloadBase


class MediaDownloadAttempt(Base):
    """Append-only ledger of every completed download attempt (success or error).

    A MediaDownloadBase row's own error_message/status/progress reflect only
    the current attempt and are reset the moment a retry starts, so without
    this a previous error would simply be lost as soon as the user clicked
    retry. Each row here is a permanent record of one attempt's outcome.
    """
    __tablename__ = "media_download_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    media_download_id: Mapped[int] = mapped_column(ForeignKey("media_downloads.id", ondelete="CASCADE"), index=True)
    is_redownload: Mapped[bool]
    # The MediaDownloadStatus this attempt ended in: "downloaded", "redownloaded" or "error"
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
