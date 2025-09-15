from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class DownloadProfileSeriesSeasonAssociation(Base):
    __tablename__ = "series_download_profile_seasons"

    # Columns
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), primary_key=True)
    series_download_profile_id: Mapped[int] = mapped_column(ForeignKey("series_download_profiles.id", ondelete="CASCADE"), primary_key=True)
    is_included: Mapped[bool]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    season: Mapped["Season"] = relationship(back_populates="download_profile_series_associations")
    download_profile_series: Mapped["DownloadProfileSeries"] = relationship(back_populates="season_associations")