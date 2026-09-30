from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, Boolean, Index, String, Text, func, UniqueConstraint
from sqlalchemy.sql.schema import ForeignKey

from backend.db import Base
from backend.db.datetime_types import UTCDateTime
from backend.db.mixins.HasMetadataMixin import HasMetadataMixin
from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_types import MediaType

if TYPE_CHECKING:
    from backend.db.models.media_item import MediaItemBase
    from backend.db.models import LocalMediaProfileBase
    from .MediaDownloadHistory import MediaDownloadHistory
    from .MediaDownloadAsset import MediaDownloadAsset


class MediaDownloadBase(HasMetadataMixin, HasTaskResourcesMixin, Base):
    """Persistent representation of a downloaded (or desired) media artifact.

    This row deliberately contains no live worker lifecycle state. TaskRun and
    TaskOperation remain authoritative for current execution, while the related
    MediaDownloadHistory rows form an append-only domain audit trail. The
    MediaDownload itself records the media/profile relationship and the file
    state that survives after execution.
    """

    __tablename__ = "media_downloads"
    __metadata_parent_table__ = "media_downloads"
    __task_resource_types__ = ("media_download",)
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": MediaType.BASE.value,
    }
    __table_args__ = (
        # A media item can only have one persistent artifact per local media profile.
        UniqueConstraint("media_item_id", "local_media_profile_id", name="uq_download_per_media_profile"),
        Index("ix_media_downloads_local_profile_id", "local_media_profile_id", "id"),
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

    # Filesystem identity exists only when WireLoft has successfully inspected a
    # physical artifact. ABSENT rows therefore have no identity, and a MISSING
    # row discovered while the file is unavailable may also have none. AVAILABLE
    # and CORRUPTED artifacts always carry the complete tuple. st_dev/st_ino are
    # decimal text rather than SQLite INTEGERs so unsigned filesystem IDs cannot
    # overflow int64.
    artifact_stat_dev: Mapped[Optional[str]] = mapped_column(String(32))
    artifact_stat_ino: Mapped[Optional[str]] = mapped_column(String(32))
    artifact_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    artifact_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))

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
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    media: Mapped["MediaItemBase"] = relationship(back_populates="downloads")
    local_media_profile: Mapped["LocalMediaProfileBase"] = relationship(back_populates="media_downloads")
    history: Mapped[list["MediaDownloadHistory"]] = relationship(
        back_populates="media_download",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MediaDownloadHistory.occurred_at.desc(), MediaDownloadHistory.id.desc()",
    )

    assets: Mapped[list["MediaDownloadAsset"]] = relationship(
        back_populates="media_download", cascade="all, delete-orphan",
        passive_deletes=True, lazy="selectin",
    )

    def asset_path(self, asset_key: str) -> str | None:
        return next((asset.path for asset in self.assets if asset.asset_key == asset_key), None)

    def set_asset_path(self, asset_key: str, kind: str, path: str | None) -> None:
        """Update a named output convenience property without duplicate storage."""
        from .MediaDownloadAsset import MediaDownloadAsset
        existing = next((asset for asset in self.assets if asset.asset_key == asset_key), None)
        if path is None:
            if existing is not None:
                self.assets.remove(existing)
        elif existing is not None:
            existing.path = path
            existing.suffix = Path(path).suffix
        else:
            self.assets.append(MediaDownloadAsset(asset_key=asset_key, kind=kind, path=path, suffix=Path(path).suffix))

    @property
    def thumbnail_path(self) -> str | None:
        return self.asset_path("artwork")

    @thumbnail_path.setter
    def thumbnail_path(self, path: str | None) -> None:
        self.set_asset_path("artwork", "thumbnail", path)

    @property
    def nfo_path(self) -> str | None:
        return self.asset_path("nfo")

    @nfo_path.setter
    def nfo_path(self, path: str | None) -> None:
        self.set_asset_path("nfo", "nfo", path)

    def __repr__(self) -> str:
        return (
            f"<MediaDownloadBase(id={self.id}, type={self.type}, artifact_status={self.artifact_status}, file_path={self.file_path!r})>"
        )
