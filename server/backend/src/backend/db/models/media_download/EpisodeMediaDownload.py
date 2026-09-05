from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .MediaDownloadBase import MediaDownloadBase
from backend.types.media_types import MediaType

if TYPE_CHECKING:
    from backend.db.models import DownloadProfileBase


class EpisodeMediaDownload(MediaDownloadBase):
    __tablename__ = "media_downloads_episode"
    __mapper_args__ = {"polymorphic_identity": MediaType.EPISODE.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("media_downloads.id", ondelete="CASCADE"), primary_key=True)
    download_profile_id: Mapped[Optional[int]] = mapped_column(ForeignKey("download_profiles.id"))
    # The episode's publish_status when the currently available artifact was
    # downloaded. This is persistent artifact metadata, not attempt state.
    downloaded_publish_status: Mapped[Optional[str]]

    # Relationships
    download_profile: Mapped[Optional["DownloadProfileBase"]] = relationship(back_populates="episode_downloads")

    def __repr__(self) -> str:
        return (
            f"<EpisodeMediaDownload(id={self.id}, download_profile_id={self.download_profile_id}, "
            f"artifact_status={self.artifact_status})>"
        )
