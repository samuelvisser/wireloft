from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.types.media_types import MediaType

from .MediaItemBase import MediaItemBase

if TYPE_CHECKING:
    from .Trailer import Trailer


class Movie(MediaItemBase):
    __tablename__ = "movies"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE.value}

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

    # A collection from the outset, even though Daily Wire currently exposes
    # at most one trailer through this flow.
    trailers: Mapped[list["Trailer"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        foreign_keys="Trailer.movie_id",
        order_by="Trailer.id",
    )

    def __repr__(self) -> str:
        return f"<Movie(id={self.id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
