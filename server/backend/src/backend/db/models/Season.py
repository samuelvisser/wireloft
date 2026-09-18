from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.datetime_types import UTCDateTime
from backend.db.mixins.HasTaskResourcesMixin import HasTaskResourcesMixin
from backend.types.season_types import SeasonType

if TYPE_CHECKING:
    from backend.db.models import Show
    from backend.db.models.media_item import Episode


class Season(Base, HasTaskResourcesMixin):
    __tablename__ = "seasons"
    __task_resource_types__ = ("season",)
    __table_args__ = (
        UniqueConstraint("show_id", "index", name="uq_season_show_index"),
        UniqueConstraint("show_id", "slug", name="uq_season_show_slug"),
    )

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))
    index: Mapped[int]
    slug: Mapped[str] = mapped_column(index=True)
    name: Mapped[str]
    season_type: Mapped[str] = mapped_column(
        default=SeasonType.NORMAL.value,
        server_default=SeasonType.NORMAL.value,
    )
    # Media-library season number. Extra collections deliberately share season 0;
    # normal seasons receive stable 1..N values independently from internal index.
    season_number: Mapped[int] = mapped_column(default=1, server_default="1")

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="seasons")
    episodes: Mapped[list["Episode"]] = relationship(back_populates="season")

    def __repr__(self):
        return (
            f"<Season(id={self.id}, slug={self.slug}, show_id={self.show_id}, "
            f"index={self.index}, season_type={self.season_type}, "
            f"season_number={self.season_number}, created_at={self.created_at}, "
            f"updated_at={self.updated_at})>"
        )
