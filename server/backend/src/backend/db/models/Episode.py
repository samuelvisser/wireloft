from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from backend.db import Base

class Episode(Base):
    __tablename__ = "episodes"

    # Fields
    id: Mapped[str] = mapped_column(primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), primary_key=True)
    uuid: Mapped[str] = mapped_column(index=True)
    dw_id: Mapped[str] = mapped_column(index=True)
    slug: Mapped[str] = mapped_column(index=True)
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
