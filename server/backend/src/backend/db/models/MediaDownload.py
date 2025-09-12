from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, func

from backend.db import Base
from backend.types import MediaDownloadStatus


class MediaDownload(Base):
    __tablename__ = "media_downloads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    download_status: Mapped[MediaDownloadStatus]
    file_path: Mapped[str]

    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<MediaDownload(id={self.id}, download_status={self.download_status}, file_path={self.file_path}, created_date={self.created_date}, modified_date={self.modified_date})>"