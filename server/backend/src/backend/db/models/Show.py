from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.types.show_types import ShowType, EpisodeIdentifier


class Show(Base):
    __tablename__ = "shows"

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(index=True, unique=True)
    dw_id: Mapped[str] = mapped_column(index=True, unique=True)
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    title: Mapped[str]
    description: Mapped[Optional[str]]
    url: Mapped[str] = mapped_column(unique=True)
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
        back_populates="show", cascade="all, delete-orphan"
    )
    download_profiles: Mapped[list["DownloadProfileBase"]] = relationship(
        back_populates="show", cascade="all, delete-orphan"
    )
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="show", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Show(id={self.id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"