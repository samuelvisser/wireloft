from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from sqlalchemy import DateTime, func

from backend.db.core import Base

if TYPE_CHECKING:
    from backend.db.models import Episode


class EpisodeVersion(Base):
    __tablename__ = "episode_versions"

    # Fields
    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    version: Mapped[str] ## FREE or MEMBER
    slug: Mapped[str]
    publish_status: Mapped[str]
    video_url: Mapped[Optional[str]]
    audio_url: Mapped[Optional[str]]
    sharing_url: Mapped[Optional[str]]
    went_live_date: Mapped[Optional[datetime]]
    published_date: Mapped[Optional[datetime]]
    scheduled_date: Mapped[Optional[datetime]]
    redownloaded_date: Mapped[Optional[datetime]]

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
    episode: Mapped["Episode"] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"<EpisodeVersion(id={self.id}, created_at={self.created_at}, updated_at={self.updated_at})>"
