from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .MovieExtra import MovieExtra


class MovieExtraSource(Base):
    """Canonical metadata for one immutable Daily Wire movie-extra clip.

    The source owns everything that is intrinsic to the clip itself. A
    movie-specific ``MovieExtra`` keeps only placement-specific state such as its
    parent movie, classification and download history.
    """

    __tablename__ = "movie_extra_sources"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_movie_extra_sources_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(
        default="",
        server_default="",
        nullable=False,
    )
    description: Mapped[Optional[str]]
    duration: Mapped[float] = mapped_column(
        default=0.0,
        server_default="0",
        nullable=False,
    )
    background_image_path: Mapped[Optional[str]]
    thumbnail_landscape_path: Mapped[Optional[str]]
    thumbnail_portrait_path: Mapped[Optional[str]]
    thumbnail_square_path: Mapped[Optional[str]]
    sharing_url: Mapped[Optional[str]]
    published_date: Mapped[Optional[datetime]]
    available_for: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )

    movie_extras: Mapped[list["MovieExtra"]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return (
            f"<MovieExtraSource(id={self.id}, slug={self.slug!r}, "
            f"title={self.title!r})>"
        )
