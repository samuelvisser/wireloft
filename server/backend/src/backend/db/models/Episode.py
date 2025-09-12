from datetime import datetime
from typing import Optional

from backend.db.models.MediaItem import MediaItem
from backend.types import EpisodePublishStatus
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, DateTime, func

from backend.types import MediaType


class Episode(MediaItem):
    __tablename__ = "episodes"
    __mapper_args__ = {"polymorphic_identity": MediaType.episode}

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), primary_key=True)
    index: Mapped[int] = mapped_column(index=True)
    publish_status: Mapped[EpisodePublishStatus]
    went_live_date: Mapped[Optional[datetime]]
    published_date: Mapped[Optional[datetime]]
    redownloaded_date: Mapped[Optional[datetime]]

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="episodes")

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, show_id={self.show_id}, slug={self.slug}, title={self.title}, created_date={self.created_date}, modified_date={self.modified_date})>"
