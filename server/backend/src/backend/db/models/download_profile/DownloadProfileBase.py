from datetime import datetime

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint, DateTime, func, JSON
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.types.download_profile_types import DownloadProfileType

if TYPE_CHECKING:
    from backend.db.models import Show, LocalMediaProfile, EpisodeMediaDownload  # or from backend.db.models import Show, Season


class DownloadProfileBase(Base):
    __tablename__ = "download_profiles"
    __table_args__ = (
        UniqueConstraint("show_id", "local_media_profile_id", name="uq_unique_media_profile_per_show"),
    )
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": DownloadProfileType.BASE.value,
    }

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))
    local_media_profile_id: Mapped[int] = mapped_column(ForeignKey("local_media_profiles.id"))
    type: Mapped[str]
    enable_profile: Mapped[bool] = mapped_column(default=True)
    ep_id_type_list: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        default=list,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="download_profiles")
    local_media_profile: Mapped["LocalMediaProfile"] = relationship(back_populates="download_profiles")

    episode_downloads: Mapped[list["EpisodeMediaDownload"]] = relationship(
        back_populates="download_profile"
    )


    def __repr__(self) -> str:
        return f"<DownloadProfileBase(id={self.id}, type={self.type}, show_id={self.show_id}, enable_profile={self.enable_profile}, created_at={self.created_at}, updated_at={self.updated_at})>"