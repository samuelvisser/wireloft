import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base

class MediaProfile(Base):
    __tablename__ = "media_profiles"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    output_template: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    preferred_format: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    download_series_images: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    created_date: Mapped[sa.DateTime] = mapped_column(sa.DateTime, nullable=False)
    modified_date: Mapped[sa.DateTime] = mapped_column(sa.DateTime, nullable=False)

    def __repr__(self) -> str:
        return f"<MediaProfile(id={self.id}, name={self.name}, created_date={self.created_date}, modified_date={self.modified_date})>"