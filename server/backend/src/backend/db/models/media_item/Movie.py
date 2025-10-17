from typing import Optional

from .MediaItemBase import MediaItemBase
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey

from backend.types.media_types import MediaType


class Movie(MediaItemBase):
    __tablename__ = "movies"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE.value}

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)
    dw_id: Mapped[Optional[str]] = mapped_column(index=True)
    slug: Mapped[str]

    def __repr__(self) -> str:
        return f"<Movie(id={self.id}, slug={self.slug}, title={self.title}, created_at={self.created_at}, updated_at={self.updated_at})>"