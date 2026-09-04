from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.media_types import MediaType, MovieExtraType

from .MediaItemBase import MediaItemBase

if TYPE_CHECKING:
    from .Movie import Movie


class MovieExtra(MediaItemBase, HasTaskResourcesMixin):
    __tablename__ = "movie_extras"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE_EXTRA.value}
    __task_resource_types__ = ("movie_extra",)

    id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    movie_extra_type: Mapped[str] = mapped_column(
        default=MovieExtraType.OTHER.value,
        server_default=MovieExtraType.OTHER.value,
        nullable=False,
    )
    dw_id: Mapped[Optional[str]] = mapped_column(index=True, unique=True)
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    sharing_url: Mapped[Optional[str]]
    published_date: Mapped[Optional[datetime]]

    movie: Mapped["Movie"] = relationship(
        back_populates="movie_extras",
        foreign_keys=[movie_id],
    )

    def __repr__(self) -> str:
        return (
            f"<MovieExtra(id={self.id}, movie_id={self.movie_id}, "
            f"movie_extra_type={self.movie_extra_type}, slug={self.slug}, "
            f"title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
        )
