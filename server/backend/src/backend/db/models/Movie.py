from backend.db.models.MediaItem import MediaItem
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey

from backend.types import MediaType


class Movie(MediaItem):
    __tablename__ = "movies"
    __mapper_args__ = {"polymorphic_identity": MediaType.movie}

    # Fields
    id: Mapped[int] = mapped_column(ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True)

    def __repr__(self) -> str:
        return f"<Movie(id={self.id}, slug={self.slug}, title={self.title}, created_date={self.created_date}, modified_date={self.modified_date})>"