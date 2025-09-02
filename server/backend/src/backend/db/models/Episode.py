from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from backend.db import Base
from backend.db.models.Show import Show


class Episode(Base):
    __tablename__ = "episodes"

    # Fields
    id: Mapped[str] = mapped_column(primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))

    uuid: Mapped[str]
    dw_id: Mapped[str]
    slug: Mapped[str]
    title: Mapped[str]
    description: Mapped[Optional[str]]
    status: Mapped[str]
    went_live_date: Mapped[Optional[str]]
    published_date: Mapped[Optional[str]]
    downloaded_date: Mapped[Optional[str]]
    redownloaded_date: Mapped[Optional[str]]
    created_date: Mapped[str]
    modified_date: Mapped[str]

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="episodes")

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, show_id={self.show_id}, slug={self.slug}, title={self.title}, created_date={self.created_date}, modified_date={self.modified_date})>"
