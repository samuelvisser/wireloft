from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, func, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.db import Base
from backend.types.stream_profile_types import StreamProfileType

if TYPE_CHECKING:
    from backend.db.models import Show


class StreamProfileBase(Base):
    __tablename__ = "stream_profiles"
    __table_args__ = (
        UniqueConstraint("show_id", "type", "preferred_format", name="uq_unique_stream_profile_type_and_format_per_show"),
    )
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": StreamProfileType.BASE.value,
    }

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))
    enable_profile: Mapped[bool] = mapped_column(default=True)

    use_downloads: Mapped[bool] = mapped_column(default=False, comment="Use local downloads for stream")
    use_dw_stream: Mapped[bool] = mapped_column(default=False, comment="Use direct DW stream endpoints for stream")
    preferred_format: Mapped[str] = mapped_column(comment="Preferred format for stream, used when choosing the correct downloaded file "
                                                          "or whether to stream audio or video from DW")
    require_exact_match: Mapped[bool] = mapped_column(comment="When allowing downloads, only allow exact matches for preferred format")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="stream_profiles")


    def __repr__(self) -> str:
        return f"<StreamProfileBase(id={self.id}, enable_profile={self.enable_profile}, use_downloads={self.use_downloads}, use_dw_stream={self.use_dw_stream}, created_at={self.created_at}, updated_at={self.updated_at})>"