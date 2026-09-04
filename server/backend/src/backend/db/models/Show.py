from datetime import datetime
from typing import Optional, TYPE_CHECKING, TypeAlias

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.db.mixins.HasMetadataMixin import HasMetadataMixin
from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin

if TYPE_CHECKING:
    from backend.db.models.media_item import Episode
    from backend.db.models.stream_profile import StreamProfileBase
    from backend.db.models import Season, PodcastDownloadProfile, SeriesDownloadProfile


class Show(Base, HasMetadataMixin, HasTaskResourcesMixin):
    __tablename__ = "shows"
    __task_resource_types__ = ("show",)

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(index=True, unique=True)
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    title: Mapped[str]
    description: Mapped[Optional[str]]
    sharing_url: Mapped[str] = mapped_column(unique=True)
    membership_level: Mapped[str]
    type: Mapped[str]
    episode_identifier: Mapped[str]
    author_name: Mapped[str]
    author_slug: Mapped[str]
    author_headshot_path: Mapped[Optional[str]]
    background_image_path: Mapped[Optional[str]]
    logo_image_path: Mapped[Optional[str]]
    thumbnail_landscape_path: Mapped[Optional[str]]
    thumbnail_portrait_path: Mapped[Optional[str]]
    thumbnail_square_path: Mapped[Optional[str]]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="show", cascade="all, delete-orphan", order_by="desc(Episode.index)"
    )
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="show", cascade="all, delete-orphan", order_by="desc(Season.index)"
    )
    download_profiles: Mapped[list["SeriesDownloadProfile | PodcastDownloadProfile"]] = relationship(
        "DownloadProfileBase",
        back_populates="show", cascade="all, delete-orphan"
    )
    stream_profiles: Mapped[list["StreamProfileBase"]] = relationship(
        back_populates="show", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Show(id={self.id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"