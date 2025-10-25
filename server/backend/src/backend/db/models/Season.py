from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship

from backend.db import Base

if TYPE_CHECKING:
    from backend.db.models import Show
    from backend.db.models.media_item import Episode


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("show_id", "index", name="uq_season_show_index"),
    )

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dw_id: Mapped[str] = mapped_column(index=True, unique=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))
    index: Mapped[int]
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    name: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="seasons")
    episodes: Mapped[list["Episode"]] = relationship(back_populates="season")

    def __repr__(self):
        return f"<Season(id={self.id}, show_id={self.show_id}, index={self.index}, slug={self.slug}, created_at={self.created_at}, updated_at={self.updated_at})>"