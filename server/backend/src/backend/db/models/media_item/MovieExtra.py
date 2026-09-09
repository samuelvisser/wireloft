from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, UniqueConstraint, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.media_types import MediaType, MovieExtraType

from .MediaItemBase import MediaItemBase
from .MovieExtraSource import MovieExtraSource

if TYPE_CHECKING:
    from .Movie import Movie


_SOURCE_METADATA_FIELDS = (
    "slug",
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
    "sharing_url",
    "published_date",
    "available_for",
)


class MovieExtra(MediaItemBase, HasTaskResourcesMixin):
    """A movie-specific placement of one globally identified extra clip.

    MovieExtra intentionally does not inherit MediaContentMetadataMixin. Its
    source owns all intrinsic clip metadata, while this MediaItem owns only the
    parent-specific placement/download identity and contextual classification.
    The proxy properties keep existing call sites independent of that storage
    normalization.
    """

    __tablename__ = "movie_extras"
    __mapper_args__ = {
        "polymorphic_identity": MediaType.MOVIE_EXTRA.value,
        "polymorphic_load": "selectin",
    }
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

    movie: Mapped["Movie"] = relationship(
        back_populates="movie_extras",
        foreign_keys=[movie_id],
    )
    source: Mapped[MovieExtraSource] = relationship(
        back_populates="movie_extras",
        lazy="joined",
        innerjoin=True,
    )

    def __init__(self, **kwargs) -> None:
        """Keep direct construction compatible with the pre-source model API."""
        source = kwargs.pop("source", None)
        source_values = {
            field: kwargs.pop(field)
            for field in _SOURCE_METADATA_FIELDS
            if field in kwargs
        }

        if source is None and source_values:
            source = MovieExtraSource(slug=source_values.get("slug", ""))
        if source is not None:
            kwargs["source"] = source

        super().__init__(**kwargs)

        # Slug first establishes/validates immutable source identity before the
        # remaining metadata is copied onto the shared source.
        for field in _SOURCE_METADATA_FIELDS:
            if field in source_values:
                setattr(self, field, source_values[field])

    def _source_for_assignment(self) -> MovieExtraSource:
        if self.source is None:
            self.source = MovieExtraSource(slug="")
        return self.source

    @hybrid_property
    def slug(self) -> str:
        return self.source.slug

    @slug.setter
    def slug(self, value: str) -> None:
        source = self._source_for_assignment()
        if source.slug and source.slug != value:
            raise ValueError("A movie extra's immutable source slug cannot be changed")
        source.slug = value

    @slug.expression
    def slug(cls):
        return (
            select(MovieExtraSource.slug)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def title(self) -> str:
        return self.source.title

    @title.setter
    def title(self, value: str) -> None:
        self._source_for_assignment().title = value

    @title.expression
    def title(cls):
        return (
            select(MovieExtraSource.title)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def description(self) -> Optional[str]:
        return self.source.description

    @description.setter
    def description(self, value: Optional[str]) -> None:
        self._source_for_assignment().description = value

    @description.expression
    def description(cls):
        return (
            select(MovieExtraSource.description)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def duration(self) -> float:
        return self.source.duration

    @duration.setter
    def duration(self, value: float) -> None:
        self._source_for_assignment().duration = value

    @duration.expression
    def duration(cls):
        return (
            select(MovieExtraSource.duration)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def background_image_path(self) -> Optional[str]:
        return self.source.background_image_path

    @background_image_path.setter
    def background_image_path(self, value: Optional[str]) -> None:
        self._source_for_assignment().background_image_path = value

    @background_image_path.expression
    def background_image_path(cls):
        return (
            select(MovieExtraSource.background_image_path)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def thumbnail_landscape_path(self) -> Optional[str]:
        return self.source.thumbnail_landscape_path

    @thumbnail_landscape_path.setter
    def thumbnail_landscape_path(self, value: Optional[str]) -> None:
        self._source_for_assignment().thumbnail_landscape_path = value

    @thumbnail_landscape_path.expression
    def thumbnail_landscape_path(cls):
        return (
            select(MovieExtraSource.thumbnail_landscape_path)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def thumbnail_portrait_path(self) -> Optional[str]:
        return self.source.thumbnail_portrait_path

    @thumbnail_portrait_path.setter
    def thumbnail_portrait_path(self, value: Optional[str]) -> None:
        self._source_for_assignment().thumbnail_portrait_path = value

    @thumbnail_portrait_path.expression
    def thumbnail_portrait_path(cls):
        return (
            select(MovieExtraSource.thumbnail_portrait_path)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def thumbnail_square_path(self) -> Optional[str]:
        return self.source.thumbnail_square_path

    @thumbnail_square_path.setter
    def thumbnail_square_path(self, value: Optional[str]) -> None:
        self._source_for_assignment().thumbnail_square_path = value

    @thumbnail_square_path.expression
    def thumbnail_square_path(cls):
        return (
            select(MovieExtraSource.thumbnail_square_path)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def sharing_url(self) -> Optional[str]:
        return self.source.sharing_url

    @sharing_url.setter
    def sharing_url(self, value: Optional[str]) -> None:
        self._source_for_assignment().sharing_url = value

    @sharing_url.expression
    def sharing_url(cls):
        return (
            select(MovieExtraSource.sharing_url)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def published_date(self) -> Optional[datetime]:
        return self.source.published_date

    @published_date.setter
    def published_date(self, value: Optional[datetime]) -> None:
        self._source_for_assignment().published_date = value

    @published_date.expression
    def published_date(cls):
        return (
            select(MovieExtraSource.published_date)
            .where(MovieExtraSource.id == cls.source_id)
            .scalar_subquery()
        )

    @hybrid_property
    def available_for(self) -> list[str]:
        return self.source.available_for

    @available_for.setter
    def available_for(self, value: list[str]) -> None:
        self._source_for_assignment().available_for = list(value)

    @available_for.expression
    def available_for(cls):
        return (
            select(MovieExtraSource.available_for)
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
