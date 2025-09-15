from sqlalchemy import ForeignKey
from sqlalchemy.ext.associationproxy import association_proxy, AssociationProxy
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db.models.DownloadProfileBase import DownloadProfileBase
from backend.db.models.DownloadProfileSeriesSeasonAssociation import DownloadProfileSeriesSeasonAssociation
from backend.types.download_profile_types import DownloadProfileType


class DownloadProfileSeries(DownloadProfileBase):
    __tablename__ = "series_download_profiles"
    __mapper_args__ = {"polymorphic_identity": DownloadProfileType.series}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("download_profiles.id", ondelete="CASCADE"), primary_key=True)
    include_upcoming_seasons: Mapped[bool]

    # Relationships
    season_associations: Mapped[list["DownloadProfileSeriesSeasonAssociation"]] = relationship(
        back_populates="download_profile_series",
        cascade="all, delete-orphan"
    )

    # Association proxies
    seasons: AssociationProxy[list["Season"]] = association_proxy(
        "season_associations",
        "season",
        creator=lambda season: DownloadProfileSeriesSeasonAssociation(season=season, is_included=True),
)


    def __repr__(self) -> str:
        return f"<DownloadProfileSeries(id={self.id}, show_id={self.show_id}, enable_profile={self.enable_profile}, created_at={self.created_at}, updated_at={self.updated_at})>"