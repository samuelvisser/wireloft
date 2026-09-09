from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, JSON, UniqueConstraint, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.media_types import MediaType, MovieExtraType

from .MediaItemBase import MediaItemBase
from .MovieExtraSource import MovieExtraSource

if TYPE_CHECKING:
    from .Movie import Movie


class MovieExtra(MediaItemBase, HasTaskResourcesMixin):
    """A movie-specific listing of one globally identified movie-extra clip.

    ``MovieExtraSource`` owns the immutable Daily Wire slug. This row stays a
    MediaItem because it represents the clip's placement under one parent movie;
    that preserves WireLoft's one-download-per-media-item-and-profile invariant.
    """

    __tablename__ = "movie_extras"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE_EXTRA.value}
    __task_resource_types__ = ("movie_extra",)
    __table_args__ = (
        UniqueConstraint(
            "movie_id",
            "source_id",
            name="uq_movie_extras_movie_id_source_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("movie_extra_sources.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    movie_extra_type: Mapped[str] = mapped_column(
        default=MovieExtraType.OTHER.value,
        server_default=MovieExtraType.OTHER.value,
        nullable=False,
    )
    sharing_url: Mapped[Optional[str]]
    published_date: Mapped[Optional[datetime]]
    available_for: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )

    movie: Mapped["Movie"] = relationship(
        back_populates="movie_extras",
        foreign_keys=[movie_id],
    )
    source: Mapped[MovieExtraSource] = relationship(
        back_populates="movie_extras",
        lazy="joined",
        innerjoin=True,
    )

    @hybrid_property
    def slug(self) -> str:
        """Return the immutable Daily Wire slug owned by the shared source."""
        return self.source.slug

    @slug.setter
    def slug(self, value: str) -> None:
        """Compatibility constructor support for isolated MovieExtra instances.

        Production indexing resolves/reuses the global source explicitly. The
        setter exists for callers that construct a standalone MovieExtra directly;
        changing the slug of an already-associated source is intentionally blocked.
        """
        if self.source is None:
            self.source = MovieExtraSource(slug=value)
            return
        if self.source.slug != value:
            raise ValueError("A movie extra's immutable source slug cannot be changed")

    @slug.expression
    def slug(cls):
        # Keep existing query call-sites such as ``MovieExtra.slug == value``
        # working while the actual value lives only on movie_extra_sources.
        return (
            select(MovieExtraSource.slug)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    def __repr__(self) -> str:
        return (
            f"<MovieExtra(id={self.id}, movie_id={self.movie_id}, "
            f"source_id={self.source_id}, movie_extra_type={self.movie_extra_type}, "
            f"slug={self.slug}, title={self.title}, created_at={self.created_at}, "
            f"updated_at={self.updated_at})>"
        )
