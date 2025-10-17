from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .MediaItemBase import MediaItemBase
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, UniqueConstraint

from backend.types.media_types import MediaType

if TYPE_CHECKING:
    from backend.db.models import Show, Season, EpisodeVersion


class Episode(MediaItemBase):
    __tablename__ = "episodes"
    __mapper_args__ = {"polymorphic_identity": MediaType.EPISODE.value}
    __table_args__ = (
        UniqueConstraint("show_id", "index", name="uq_episode_show_index"),
    )

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    index: Mapped[int]

    # Relationships
    versions: Mapped[list["EpisodeVersion"]] = relationship(back_populates="episode")
    show: Mapped["Show"] = relationship(back_populates="episodes")
    season: Mapped["Season"] = relationship(back_populates="episodes")

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, show_id={self.show_id}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
