from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, func
from sqlalchemy.orm import mapped_column, Mapped, relationship

from backend.db import Base


class Season(Base):
    __tablename__ = "seasons"

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dw_id: Mapped[str] = mapped_column(index=True, unique=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))
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
