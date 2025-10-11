from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.models import MediaDownloadBase
from backend.types.media_types import MediaType


class EpisodeMediaDownload(MediaDownloadBase):
    __tablename__ = "episode_media_downloads"
    __mapper_args__ = {"polymorphic_identity": MediaType.EPISODE.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("media_downloads.id", ondelete="CASCADE"), primary_key=True)
    download_profile_id: Mapped[Optional[int]] = mapped_column(ForeignKey("download_profiles.id"))

    # Relationships
    download_profile: Mapped[Optional["DownloadProfile"]] = relationship(back_populates="episode_downloads")


    def __repr__(self) -> str:
        return f"<EpisodeMediaDownload(id={self.id}, download_profile_id={self.download_profile_id}, created_at={self.created_at}, updated_at={self.updated_at})>"