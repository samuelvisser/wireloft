from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .MediaItemBase import MediaItemBase
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, UniqueConstraint

from backend.types.media_types import MediaType
from backend.db.mixins.HasMetadataMixin import HasMetadataMixin

if TYPE_CHECKING:
    from backend.db.models import Show, Season


class Episode(MediaItemBase, HasMetadataMixin):
    __tablename__ = "episodes"
    __mapper_args__ = {"polymorphic_identity": MediaType.EPISODE.value}
    __table_args__ = (
        UniqueConstraint("show_id", "index", name="uq_episode_show_index"),
        UniqueConstraint("show_id", "episode_identifier", name="uq_unique_episode_identifier_per_show"),
    )

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    dw_id: Mapped[Optional[str]] = mapped_column(index=True, unique=True)
    index: Mapped[int]
    episode_identifier: Mapped[str] = mapped_column(comment="Unique identifier that is used to identify the episode within the show")
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    publish_status: Mapped[str]
    video_url: Mapped[Optional[str]]
    audio_url: Mapped[Optional[str]]
    sharing_url: Mapped[str]
    went_live_date: Mapped[Optional[datetime]]
    published_date: Mapped[Optional[datetime]]
    scheduled_date: Mapped[Optional[datetime]]
    redownloaded_date: Mapped[Optional[datetime]]

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="episodes")
    season: Mapped["Season"] = relationship(back_populates="episodes")

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, show_id={self.show_id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
