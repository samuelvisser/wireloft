from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.datetime_types import UTCDateTime

if TYPE_CHECKING:
    from .MediaDownloadBase import MediaDownloadBase


class MediaDownloadHistory(Base):
    """Append-only history of user-meaningful changes to one media download."""

    __tablename__ = "media_download_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    media_download_id: Mapped[int] = mapped_column(
        ForeignKey("media_downloads.id", ondelete="CASCADE"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32), index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        index=True,
    )

    media_download: Mapped["MediaDownloadBase"] = relationship(back_populates="history")

    def __repr__(self) -> str:
        return (
            f"<MediaDownloadHistory(id={self.id}, media_download_id={self.media_download_id}, action={self.action!r}, occurred_at={self.occurred_at})>"
        )
