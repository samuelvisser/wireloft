from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.types.media_types import MediaType

from .MediaItemBase import MediaItemBase

if TYPE_CHECKING:
    from .Movie import Movie


class Trailer(MediaItemBase):
    __tablename__ = "trailers"
    __mapper_args__ = {"polymorphic_identity": MediaType.TRAILER.value}

    id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    dw_id: Mapped[Optional[str]] = mapped_column(index=True, unique=True)
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    sharing_url: Mapped[Optional[str]]

    movie: Mapped["Movie"] = relationship(
        back_populates="trailers",
        foreign_keys=[movie_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Trailer(id={self.id}, movie_id={self.movie_id}, slug={self.slug}, "
            f"title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"
        )
