from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Boolean, DateTime, String, Text, func, UniqueConstraint
from sqlalchemy.sql.schema import ForeignKey

from backend.db import Base
from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_types import MediaType

if TYPE_CHECKING:
    from backend.db.models.media_item import MediaItemBase
    from backend.db.models import LocalMediaProfileBase


class MediaDownloadBase(HasTaskResourcesMixin, Base):
    """Persistent representation of a downloaded (or desired) media artifact.

    This row deliberately contains no worker lifecycle state. Queued/running/
    failed/canceled attempts, progress, retries and timing are TaskRun and
    TaskOperation concerns. The MediaDownload only records the media/profile
    relationship and the file state that survives after execution.
    """

    __tablename__ = "media_downloads"
    __task_resource_types__ = ("media_download",)
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": MediaType.BASE.value,
    }
    __table_args__ = (
        # A media item can only have one persistent artifact per local media profile.
        UniqueConstraint("media_item_id", "local_media_profile_id", name="uq_download_per_media_profile"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]
    media_item_id: Mapped[int] = mapped_column(ForeignKey("media_items.id"))
    local_media_profile_id: Mapped[int] = mapped_column(ForeignKey("local_media_profiles.id"))

    file_path: Mapped[str]
    artifact_status: Mapped[str] = mapped_column(
        String(24),
        default=MediaDownloadArtifactStatus.ABSENT.value,
        server_default=MediaDownloadArtifactStatus.ABSENT.value,
        index=True,
    )
    artifact_error: Mapped[Optional[str]] = mapped_column(Text)
    # A user cancellation prevents an automatic Download Profile sweep from
    # immediately recreating the same operation. An explicit Retry/Download
    # request clears this flag. This is user intent, not execution state.
    automatic_retry_suppressed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )

    # Facts about the currently available artifact. They are only replaced
    # after a successful download attempt.
    downloaded_bytes: Mapped[Optional[int]]
    format_downloaded: Mapped[Optional[str]]
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    media: Mapped["MediaItemBase"] = relationship(back_populates="downloads")
    local_media_profile: Mapped["LocalMediaProfileBase"] = relationship(back_populates="media_downloads")

    def __repr__(self) -> str:
        return (
            f"<MediaDownloadBase(id={self.id}, type={self.type}, "
            f"artifact_status={self.artifact_status}, file_path={self.file_path!r})>"
        )
