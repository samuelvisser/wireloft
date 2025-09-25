from sqlalchemy import ForeignKey, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.models.DownloadProfileBase import DownloadProfileBase
from backend.types.download_profile_types import DownloadProfileType

association_table = Table(
    "series_download_profile_seasons",
    Base.metadata,
    Column("series_download_profile_id", ForeignKey("series_download_profiles.id")),
    Column("season_id", ForeignKey("seasons.id")),
)

class DownloadProfileSeries(DownloadProfileBase):
    __tablename__ = "series_download_profiles"
    __mapper_args__ = {"polymorphic_identity": DownloadProfileType.SERIES.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("download_profiles.id", ondelete="CASCADE"), primary_key=True)
    include_upcoming_seasons: Mapped[bool]

    # Relationships
    seasons: Mapped[list["Season"]] = relationship(secondary=association_table)

    def __repr__(self) -> str:
        return f"<DownloadProfileSeries(id={self.id}, show_id={self.show_id}, enable_profile={self.enable_profile}, created_at={self.created_at}, updated_at={self.updated_at})>"