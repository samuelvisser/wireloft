from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.media_types import MediaType, MovieExtraType

from .MediaItemBase import MediaItemBase
from .MovieExtraSource import MovieExtraSource

if TYPE_CHECKING:
    from .Movie import Movie


class MovieExtra(MediaItemBase, HasTaskResourcesMixin):
    """A movie-specific placement of one globally identified extra clip.

    MovieExtra intentionally does not inherit MediaContentMetadataMixin. Its
    source owns all intrinsic clip metadata, while this MediaItem owns only the
    parent-specific placement/download identity and contextual classification.
    Association proxies keep callers independent of that storage normalization.
    """

    __tablename__ = "media_items_movie_extra"
    __mapper_args__ = {
        "polymorphic_identity": MediaType.MOVIE_EXTRA.value,
        "polymorphic_load": "selectin",
    }
    __task_resource_types__ = ("movie_extra",)
    __table_args__ = (
        UniqueConstraint("movie_id", "source_id", name="uq_movie_extras_movie_id_source_id"),
        Index("ix_movie_extras_movie_id", "movie_id"),
        Index("ix_movie_extras_source_id", "source_id"),
        PrimaryKeyConstraint("id", name="pk_movie_extras"),
    )

    # Table fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE",
            name="fk_movie_extras_id_media_items",), primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("media_items_movie.id",
            ondelete="CASCADE", name="fk_movie_extras_movie_id_movies",
        ), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("movie_extra_sources.id", ondelete="RESTRICT", name="fk_movie_extras_source_id_movie_extra_sources",
        ), nullable=False)
    movie_extra_type: Mapped[str] = mapped_column(default=MovieExtraType.OTHER.value, server_default=MovieExtraType.OTHER.value, nullable=False)

    # Relationships
    movie: Mapped["Movie"] = relationship(back_populates="movie_extras", foreign_keys=[movie_id])
    source: Mapped[MovieExtraSource] = relationship(back_populates="movie_extras", lazy="joined", innerjoin=True)

    # Related table fields
    slug: AssociationProxy[str] = association_proxy("source", "slug")
    title: AssociationProxy[str] = association_proxy("source", "title")
    description: AssociationProxy[Optional[str]] = association_proxy("source", "description")
    duration: AssociationProxy[float] = association_proxy("source", "duration")
    background_image_path: AssociationProxy[Optional[str]] = association_proxy("source", "background_image_path")
    thumbnail_landscape_path: AssociationProxy[Optional[str]] = association_proxy("source", "thumbnail_landscape_path")
    thumbnail_portrait_path: AssociationProxy[Optional[str]] = association_proxy("source", "thumbnail_portrait_path")
    thumbnail_square_path: AssociationProxy[Optional[str]] = association_proxy("source", "thumbnail_square_path")
    sharing_url: AssociationProxy[Optional[str]] = association_proxy("source", "sharing_url")
    published_date: AssociationProxy[Optional[datetime]] = association_proxy("source", "published_date")
    available_for: AssociationProxy[list[str]] = association_proxy("source", "available_for")

    def __init__(self, **kwargs) -> None:
        """Keep direct construction compatible with the pre-source model API."""
        source = kwargs.pop("source", None)
        source_columns = MovieExtraSource.__table__.columns
        source_values = {
            field: kwargs.pop(field)
            for field in tuple(kwargs)
            if field != "id" and field in source_columns
        }

        if source is None and source_values:
            source_values.setdefault("slug", "")
            source = MovieExtraSource(**source_values)
            source_values = {}
        if source is not None:
            kwargs["source"] = source

        super().__init__(**kwargs)

        for field, value in source_values.items():
            setattr(self, field, value)

    def __repr__(self) -> str:
        return (
            f"<MovieExtra(id={self.id}, movie_id={self.movie_id}, source_id={self.source_id}, movie_extra_type={self.movie_extra_type}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
        )
