from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .MediaItemBase import MediaItemBase
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Boolean, ForeignKey, Index, PrimaryKeyConstraint, UniqueConstraint, text

from backend.types.episode_types import EpisodePublishStatus
from backend.types.media_types import MediaType
from backend.db.mixins.HasMetadataMixin import HasMetadataMixin
from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.db.mixins.MediaContentMetadataMixin import MediaContentMetadataMixin
from backend.utils.episode import EpisodeIdentifierInfo
from backend.utils.episode_publication_timing import (
    TRUSTED_LIVE_ENDED_META_KEY,
    TRUSTED_PUBLISHED_FINAL_META_KEY,
    safe_live_ended_from_meta,
    safe_published_final_from_meta,
)
from backend.utils.episode_slug import is_no_show_today_slug

if TYPE_CHECKING:
    from backend.db.models import Show, Season


class Episode(
    MediaItemBase,
    MediaContentMetadataMixin,
    HasMetadataMixin,
    HasTaskResourcesMixin,
):
    __tablename__ = "media_items_episode"
    __mapper_args__ = { "polymorphic_identity": MediaType.EPISODE.value, "polymorphic_load": "selectin"}
    __task_resource_types__ = ("episode",)
    __table_args__ = (
        UniqueConstraint("show_id", "index", name="uq_episode_show_index"),
        UniqueConstraint("show_id", "episode_identifier", name="uq_unique_episode_identifier_per_show"),
        Index(
            "ix_media_items_episode_show_published_id",
            "show_id",
            "published_date",
            "id",
        ),
        Index(
            "ix_media_items_episode_show_publish_status",
            "show_id",
            "publish_status",
        ),
        Index(
            "ix_media_items_episode_season_index_id",
            "season_id",
            "index",
            "id",
        ),
        Index(
            "ix_media_items_episode_unfinished_metadata_status",
            "publish_status",
            sqlite_where=text("metadata_is_final = 0"),
        ),
        PrimaryKeyConstraint("id", "show_id", name="pk_episodes"),
    )

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"),primary_key=True,)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    index: Mapped[int]
    episode_identifier: Mapped[str] = mapped_column(comment="Unique identifier that is used to identify the episode within the show")
    dw_episode_number: Mapped[Optional[str]] = mapped_column(comment="Episode number exactly as returned by The Daily Wire")
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

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="episodes")
    season: Mapped["Season"] = relationship(back_populates="episodes")

    @property
    def safe_live_ended(self) -> datetime | None:
        """Trusted observed end of LIVE, or None when WireLoft cannot prove it."""
        return safe_live_ended_from_meta(
            self.get_meta(TRUSTED_LIVE_ENDED_META_KEY)
        )

    @property
    def safe_published_final(self) -> datetime | None:
        """Trusted observed transition to PUBLISHED_FINAL, or None if unknown."""
        return safe_published_final_from_meta(
            self.get_meta(TRUSTED_PUBLISHED_FINAL_META_KEY)
        )

    @property
    def episode_identifier_info(self) -> EpisodeIdentifierInfo:
        return EpisodeIdentifierInfo.from_identifier(self.episode_identifier)

    @property
    def episode_type(self) -> str | None:
        return self.episode_identifier_info.type

    @property
    def episode_extra_type(self) -> str | None:
        return self.episode_identifier_info.extra_type

    @property
    def episode_number(self) -> str | None:
        return self.episode_identifier_info.episode_number

    @property
    def episode_sub_number(self) -> str | None:
        return self.episode_identifier_info.sub_episode_number

    @property
    def episode_label(self) -> str:
        return self.episode_identifier_info.label

    @property
    def is_no_show_today(self) -> bool:
        """Whether the stable Daily Wire slug marks this as a No Show Today placeholder."""
        return is_no_show_today_slug(self.slug)

    @property
    def early_delete_available(self) -> bool:
        """Whether the latest Daily Wire verification reported this episode missing."""
        return (
            self.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value
            and self.get_meta("no_usable_media.reason") == "not_found"
        )

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, slug={self.slug}, show_id={self.show_id}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
