from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db.models.DownloadProfileBase import DownloadProfileBase
from backend.types.download_profile_types import DownloadProfileType


class DownloadProfilePodcast(DownloadProfileBase):
    __tablename__ = "podcast_download_profiles"
    __mapper_args__ = {"polymorphic_identity": DownloadProfileType.PODCAST.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("download_profiles.id", ondelete="CASCADE"), primary_key=True)
    download_with_countdown: Mapped[bool] = mapped_column(default=False)
    redownload_final: Mapped[bool] = mapped_column(default=False)
    download_days_in_past: Mapped[int] = mapped_column(default=0)
    delete_older_episodes: Mapped[bool] = mapped_column(default=True)

    def __repr__(self) -> str:
        return f"<DownloadProfilePodcast(id={self.id}, show_id={self.show_id}, enable_profile={self.enable_profile}, download_days_in_past={self.download_days_in_past}, delete_older_episodes={self.delete_older_episodes}, created_at={self.created_at}, updated_at={self.updated_at})>"