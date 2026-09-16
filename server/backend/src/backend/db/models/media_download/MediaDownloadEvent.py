from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.db.datetime_types import UTCDateTime


class MediaDownloadEvent(Base):
    """Durable non-task lifecycle event for a MediaDownload artifact."""

    __tablename__ = "media_download_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    media_download_id: Mapped[int] = mapped_column(
        ForeignKey("media_downloads.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(24), index=True)
    file_path: Mapped[str]
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        index=True,
    )
