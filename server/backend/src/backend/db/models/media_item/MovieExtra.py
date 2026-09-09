from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    ForeignKey,
    UniqueConstraint,
    event,
    inspect as sa_inspect,
    select,
)
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.media_types import MediaType, MovieExtraType

from .MediaItemBase import MediaItemBase
from .MovieExtraSource import MovieExtraSource

if TYPE_CHECKING:
    from .Movie import Movie


class MovieExtra(MediaItemBase, HasTaskResourcesMixin):
    """A movie-specific placement of one globally identified extra clip.

    MovieExtra records are unique within WireLoft in that the media it represents
    might be shared over multiple movies. Therefore, MovieExtra does not directly represent
    the media itself and intentionally does not use the MediaContentMetadataMixin.

    A MovieExtra is always connected to a MovieExtraSource, which does represent the actual
    media and is unique by its slug. To make this easier to use for callers, all fields in
    MovieExtraSource are accessible through MovieExtra with association_proxy relations.
    """

    __tablename__ = "media_items_movie_extra"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE_EXTRA.value, "polymorphic_load": "selectin"}
    __task_resource_types__ = ("movie_extra",)
    __table_args__ = (
        UniqueConstraint("movie_id", "source_id"),
    )

    # Table fields
    id: Mapped[int] = mapped_column(
        ForeignKey(
            "media_items.id",
            ondelete="CASCADE"
        ),
        primary_key=True,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey(
            "media_items_movie.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "movie_extra_sources.id",
            ondelete="RESTRICT"
        ),
        nullable=False,
        index=True
    )
    movie_extra_type: Mapped[str] = mapped_column(
        default=MovieExtraType.OTHER.value,
        server_default=MovieExtraType.OTHER.value,
        nullable=False,
    )

    # Relationships
    movie: Mapped["Movie"] = relationship(
        back_populates="movie_extras",
        foreign_keys=[movie_id],
    )
    source: Mapped[MovieExtraSource] = relationship(
        back_populates="movie_extras",
        lazy="joined",
        innerjoin=True,
    )

    # Source-owned fields exposed transparently on the placement.
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
        """Allow callers to construct an extra without knowing about its source."""
        source = kwargs.pop("source", None)
        source_columns = MovieExtraSource.__table__.columns
        source_values = {
            field: kwargs.pop(field)
            for field in tuple(kwargs)
            if field != "id" and field in source_columns
        }

        if source is None and source_values:
            source = MovieExtraSource(**source_values)
            source_values = {}
        if source is not None:
            kwargs["source"] = source

        super().__init__(**kwargs)

        for field, value in source_values.items():
            setattr(self, field, value)

    def __repr__(self) -> str:
        return (
            f"<MovieExtra(id={self.id}, movie_id={self.movie_id}, "
            f"source_id={self.source_id}, movie_extra_type={self.movie_extra_type}, "
            f"slug={self.slug}, title={self.title}, created_at={self.created_at}, "
            f"updated_at={self.updated_at})>"
        )


@event.listens_for(Session, "before_flush")
def _resolve_movie_extra_sources(
    session: Session,
    _flush_context,
    _instances,
) -> None:
    """Reuse canonical source rows for newly attached MovieExtra placements.

    Constructing ``MovieExtra(slug=..., title=...)`` creates a source-shaped
    object locally so callers can ignore the storage normalization. Immediately
    before flush, resolve those objects by slug against both persisted sources and
    other new extras in the same unit of work, merge their useful metadata, and
    point every placement at the one canonical source row.
    """
    extras = [item for item in list(session.new) if isinstance(item, MovieExtra)]
    candidates = [
        extra.source
        for extra in extras
        if extra.source is not None and extra.source.slug
    ]
    if not candidates:
        return

    slugs = {source.slug for source in candidates}
    sources_by_slug = {
        source.slug: source
        for source in session.scalars(
            select(MovieExtraSource).where(MovieExtraSource.slug.in_(slugs))
        )
    }

    for extra in extras:
        candidate = extra.source
        if candidate is None or not candidate.slug:
            continue

        source = sources_by_slug.get(candidate.slug)
        if source is None:
            sources_by_slug[candidate.slug] = candidate
            continue
        if source is candidate:
            continue

        source.merge_metadata(candidate)
        extra.source = source

        # The constructor-created candidate was attached through relationship
        # cascade. Once no placement references it, prevent a duplicate insert.
        if sa_inspect(candidate).pending and not candidate.movie_extras:
            session.expunge(candidate)
