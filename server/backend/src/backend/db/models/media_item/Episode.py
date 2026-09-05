from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .MediaItemBase import MediaItemBase
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy import Boolean, ForeignKey, UniqueConstraint

from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType
from backend.db.mixins.HasMetadataMixin import HasMetadataMixin
from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin

if TYPE_CHECKING:
    from backend.db.models import Show, Season


class Episode(MediaItemBase, HasMetadataMixin, HasTaskResourcesMixin):
    __tablename__ = "episodes"
    __mapper_args__ = {"polymorphic_identity": MediaType.EPISODE.value}
    __task_resource_types__ = ("episode",)
    __table_args__ = (
        UniqueConstraint("show_id", "index", name="uq_episode_show_index"),
        UniqueConstraint("show_id", "episode_identifier", name="uq_unique_episode_identifier_per_show"),
    )

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    index: Mapped[int]
    episode_identifier: Mapped[str] = mapped_column(comment="Unique identifier that is used to identify the episode within the show")
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    publish_status: Mapped[str]
    metadata_is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    video_url: Mapped[Optional[str]]
    audio_url: Mapped[Optional[str]]
    sharing_url: Mapped[str]
    went_live_date: Mapped[Optional[datetime]]
    published_date: Mapped[Optional[datetime]]
    scheduled_date: Mapped[Optional[datetime]]
    redownloaded_date: Mapped[Optional[datetime]]
    # Daily Wire publishes placeholder entries titled "... - No Show Today" on
    # days a show doesn't air. The flag records why a DW_PROCESSING row is known
    # to be disposable; media eligibility itself relies only on publish_status.
    is_no_show_today: Mapped[Optional[bool]]

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="episodes")
    season: Mapped["Season"] = relationship(back_populates="episodes")

    @validates("is_no_show_today")
    def _keep_no_show_status_unusable(self, _key: str, value: Optional[bool]) -> Optional[bool]:
        """Keep the model invariant that a known placeholder is never playable."""
        if value:
            self.publish_status = EpisodePublishStatus.DW_PROCESSING.value
            self.metadata_is_final = False
        return value

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, slug={self.slug}, show_id={self.show_id}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
