from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base

class Show(Base):
    __tablename__ = "shows"

    # Columns
    id: Mapped[str] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(index=True)
    dw_id: Mapped[str] = mapped_column(index=True)
    slug: Mapped[str] = mapped_column(index=True)
    media_profile_id: Mapped[int] = mapped_column(ForeignKey("media_profiles.id"))
    title: Mapped[str]
    description: Mapped[Optional[str]] = mapped_column(String(10000))
    url: Mapped[str] = mapped_column(String(510))
    status: Mapped[str]
    media_type: Mapped[str]
    author_name: Mapped[str]
    author_slug: Mapped[str]
    author_headshot_path: Mapped[Optional[str]] = mapped_column(String(510))
    download_media: Mapped[int]
    download_delay_minutes: Mapped[int]
    redownload_delay_minutes: Mapped[int]
    download_days_in_past: Mapped[int]
    delete_older_episodes: Mapped[int]
    title_filter: Mapped[Optional[str]]
    background_image_path: Mapped[Optional[str]] = mapped_column(String(510))
    logo_image_path: Mapped[Optional[str]] = mapped_column(String(510))
    thumbnail_landscape_path: Mapped[Optional[str]] = mapped_column(String(510))
    thumbnail_portrait_path: Mapped[Optional[str]] = mapped_column(String(510))
    thumbnail_square_path: Mapped[Optional[str]] = mapped_column(String(510))
    created_date: Mapped[datetime]
    modified_date: Mapped[datetime]

    # Relationships
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="show", cascade="all, delete-orphan"
    )
    media_profile: Mapped["MediaProfile"] = relationship(back_populates="shows")

    def __repr__(self) -> str:
        return f"<Show(id={self.id}, uuid={self.uuid}, dw_id={self.dw_id}, slug={self.slug}, title={self.title}, created_date={self.created_date}, modified_date={self.modified_date})>"