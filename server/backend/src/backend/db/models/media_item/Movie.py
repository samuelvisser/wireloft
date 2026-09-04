from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.media_types import MediaType

from .MediaItemBase import MediaItemBase

if TYPE_CHECKING:
    from .MovieExtra import MovieExtra


class Movie(MediaItemBase, HasTaskResourcesMixin):
    __tablename__ = "movies"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE.value}
    __task_resource_types__ = ("movie",)

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    slug: Mapped[str]
    extended_title: Mapped[Optional[str]]
    dw_id: Mapped[Optional[str]] = mapped_column(index=True, unique=True)
    sharing_url: Mapped[Optional[str]]
    author_name: Mapped[Optional[str]]
    author_slug: Mapped[Optional[str]]
    logo_image_path: Mapped[Optional[str]]
    mature_rating: Mapped[Optional[str]]

    is_downloadable: Mapped[Optional[bool]]
    available_for: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )

    release_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    release_date_source: Mapped[Optional[str]]
    release_date_source_id: Mapped[Optional[str]]
    release_date_lookup_status: Mapped[str] = mapped_column(
        default="pending",
        server_default="pending",
        nullable=False,
    )
    release_date_lookup_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    release_date_lookup_error: Mapped[Optional[str]]

    official_trailer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "movie_extras.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_movies_official_trailer_id_movie_extras",
        ),
        unique=True,
        nullable=True,
    )

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