from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .MovieExtra import MovieExtra


class MovieExtraSource(Base):
    """Global identity for one immutable Daily Wire movie-extra clip slug.

    A source is not itself a downloadable WireLoft media item. Each movie-specific
    listing remains a distinct ``MovieExtra`` media item so downloads continue to
    be scoped to one parent movie and one Local Media Profile.
    """

    __tablename__ = "movie_extra_sources"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_movie_extra_sources_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(nullable=False)

    movie_extras: Mapped[list["MovieExtra"]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<MovieExtraSource(id={self.id}, slug={self.slug!r})>"
