from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.models.StreamProfileBase import StreamProfileBase
from backend.types.stream_profile_types import StreamProfileType


class ShowStreamProfile(StreamProfileBase):
    __tablename__ = "show_stream_profiles"
    __mapper_args__ = {"polymorphic_identity": StreamProfileType.SHOW.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("stream_profiles.id", ondelete="CASCADE"), primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"))

    # Relationships
    show: Mapped["Show"] = relationship(back_populates="show_stream_profiles")


    def __repr__(self) -> str:
        return f"<ShowStreamProfile(id={self.id}, show_id={self.show_id}, enable_profile={self.enable_profile}, created_at={self.created_at}, updated_at={self.updated_at})>"