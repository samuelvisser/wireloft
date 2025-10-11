from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.models.StreamProfileBase import StreamProfileBase
from backend.types.stream_profile_types import StreamProfileType


class DownloadStreamProfile(StreamProfileBase):
    __tablename__ = "download_stream_profiles"
    __mapper_args__ = {"polymorphic_identity": StreamProfileType.DOWNLOAD.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("stream_profiles.id", ondelete="CASCADE"), primary_key=True)
    download_profile_id: Mapped[int] = mapped_column(ForeignKey("download_profiles.id"))

    # Relationships
    download_profile: Mapped["DownloadProfileBase"] = relationship(back_populates="download_stream_profiles")


    def __repr__(self) -> str:
        return f"<DownloadStreamProfile(id={self.id}, download_profile_id={self.download_profile_id}, enable_profile={self.enable_profile}, created_at={self.created_at}, updated_at={self.updated_at})>"