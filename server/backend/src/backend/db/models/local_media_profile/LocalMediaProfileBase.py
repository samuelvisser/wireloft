from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.types.local_media_profile_types import LocalMediaProfileType

if TYPE_CHECKING:
    from backend.db.models.download_profile import DownloadProfileBase
    from backend.db.models.media_download import MediaDownloadBase


class LocalMediaProfileBase(Base):
    __tablename__ = "local_media_profiles"
    __table_args__ = (
        Index(
            "uq_local_media_profiles_type_output_template_preferred_format",
            "type",
            "output_template",
            "preferred_format",
            unique=True,
        ),
    )
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": LocalMediaProfileType.BASE.value,
    }

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(
        default=LocalMediaProfileType.SHOW.value,
        server_default=LocalMediaProfileType.SHOW.value,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    name: Mapped[str] = mapped_column(unique=True)
    output_template: Mapped[str]
    preferred_format: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    download_profiles: Mapped[list["DownloadProfileBase"]] = relationship(
        back_populates="local_media_profile"
    )
    media_downloads: Mapped[list["MediaDownloadBase"]] = relationship(
        back_populates="local_media_profile"
    )

    def __repr__(self) -> str:
        return (
            f"<LocalMediaProfileBase(id={self.id}, type={self.type}, slug={self.slug}, "
            f"name={self.name}, created_at={self.created_at}, updated_at={self.updated_at})>"
        )
