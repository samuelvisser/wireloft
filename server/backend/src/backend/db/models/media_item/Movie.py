from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, ForeignKey, Index, JSON, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.datetime_types import UTCDateTime
from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.db.mixins.MediaContentMetadataMixin import MediaContentMetadataMixin
from backend.types.media_types import MediaType

from .MediaItemBase import MediaItemBase

if TYPE_CHECKING:
    from .MovieExtra import MovieExtra


class Movie(MediaItemBase, MediaContentMetadataMixin, HasTaskResourcesMixin):
    __tablename__ = "media_items_movies"
    __mapper_args__ = {
        "polymorphic_identity": MediaType.MOVIE.value,
        "polymorphic_load": "selectin",
    }
    __task_resource_types__ = ("movie",)
    __table_args__ = (
        Index("ix_movies_slug", "slug", unique=True),
        UniqueConstraint(
            "official_trailer_id",
            name="uq_movies_official_trailer_id",
        ),
        PrimaryKeyConstraint("id", name="pk_movies"),
    )

    # Fields
    id: Mapped[int] = mapped_column(
        ForeignKey(
            "media_items.id",
            ondelete="CASCADE",
            name="fk_movies_id_media_items",
        ),
        primary_key=True,
    )
    slug: Mapped[str]
    extended_title: Mapped[Optional[str]]
    sharing_url: Mapped[Optional[str]]
    author_name: Mapped[Optional[str]]
    author_slug: Mapped[Optional[str]]
    logo_image_path: Mapped[Optional[str]]
    mature_rating: Mapped[Optional[str]]

    has_video: Mapped[bool] = mapped_column(default=False, server_default="0")
    is_downloadable: Mapped[Optional[bool]]
    status: Mapped[Optional[str]]
    published_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    background: Mapped[Optional[str]]
    byline: Mapped[Optional[str]]
    language: Mapped[Optional[str]]
    origin_country: Mapped[Optional[str]]
    images: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    available_for: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )
    cast_and_crew: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )
    directed_by: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    genres: Mapped[list[Any]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    hosts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    production_companies: Mapped[list[Any]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    starring: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    written_by: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)

    # A release date is calendar data, not an instant; keep it timezone-free.
    release_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    release_date_source: Mapped[Optional[str]]
    release_date_source_id: Mapped[Optional[str]]
    release_date_lookup_status: Mapped[str] = mapped_column(
        default="pending",
        server_default="pending",
        nullable=False,
    )
    release_date_lookup_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )
    release_date_lookup_error: Mapped[Optional[str]]

    official_trailer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "media_items_movie_extras.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_movies_official_trailer_id_movie_extras",
        ),
        nullable=True,
    )

    # Relationships
    movie_extras: Mapped[list["MovieExtra"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        foreign_keys="MovieExtra.movie_id",
        order_by="MovieExtra.id",
    )
    official_trailer: Mapped[Optional["MovieExtra"]] = relationship(
        foreign_keys=[official_trailer_id],
        uselist=False,
        post_update=True,
    )

    def __repr__(self) -> str:
        return f"<Movie(id={self.id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
