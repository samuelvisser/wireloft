from datetime import datetime
from typing import Optional

from backend.db.models.MediaItem import MediaItem
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, DateTime, func

from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType


class Episode(MediaItem):
    __tablename__ = "episodes"
    __mapper_args__ = {"polymorphic_identity": MediaType.EPISODE}

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    index: Mapped[int] = mapped_column(index=True)
    publish_status: Mapped[str]
    went_live_date: Mapped[Optional[datetime]]
    published_date: Mapped[Optional[datetime]]
    redownloaded_date: Mapped[Optional[datetime]]

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="episodes")
    season: Mapped["Season"] = relationship(back_populates="episodes")

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, show_id={self.show_id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
