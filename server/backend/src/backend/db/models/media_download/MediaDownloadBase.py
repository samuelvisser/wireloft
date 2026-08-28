from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime, func, UniqueConstraint
from sqlalchemy.sql.schema import ForeignKey

from backend.db import Base
from backend.types.media_types import MediaType

if TYPE_CHECKING:
    from backend.db.models.media_item import MediaItemBase
    from backend.db.models import LocalMediaProfile
    from .MediaDownloadAttempt import MediaDownloadAttempt


class MediaDownloadBase(Base):
    __tablename__ = "media_downloads"
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": MediaType.BASE.value,
    }
    __table_args__ = (
        # A media item can only be downloaded once per local media profile
        UniqueConstraint("media_item_id", "local_media_profile_id", name="uq_download_per_media_profile"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]
    media_item_id: Mapped[int] = mapped_column(ForeignKey("media_items.id"))
    local_media_profile_id: Mapped[int] = mapped_column(ForeignKey("local_media_profiles.id"))
    download_status: Mapped[str]
    file_path: Mapped[str]
    progress: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[Optional[str]]
    downloaded_bytes: Mapped[Optional[int]]
    # What was actually fetched, e.g. "1920x1080" or "audio"
    format_downloaded: Mapped[Optional[str]]
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    media: Mapped["MediaItemBase"] = relationship(back_populates="downloads")
    local_media_profile: Mapped["LocalMediaProfile"] = relationship(back_populates="media_downloads")
    attempts: Mapped[List["MediaDownloadAttempt"]] = relationship(
        back_populates="media_download", cascade="all, delete-orphan", order_by="MediaDownloadAttempt.id.desc()"
    )


    def __repr__(self) -> str:
        return f"<MediaDownloadBase(id={self.id}, type={self.type}, download_status={self.download_status}, file_path={self.file_path}, created_at={self.created_at}, updated_at={self.updated_at})>"
