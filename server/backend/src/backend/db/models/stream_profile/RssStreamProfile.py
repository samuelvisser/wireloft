from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .StreamProfileBase import StreamProfileBase
from backend.types.stream_profile_types import (
    DEFAULT_RSS_DW_VIDEO_METHOD,
    StreamProfileType,
)


class RssStreamProfile(StreamProfileBase):
    __tablename__ = "stream_profiles_rss"
    __mapper_args__ = {"polymorphic_identity": StreamProfileType.RSS.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("stream_profiles.id", ondelete="CASCADE"), primary_key=True)
    feed_url: Mapped[str]
    dw_video_method: Mapped[str] = mapped_column(default=DEFAULT_RSS_DW_VIDEO_METHOD)

    def __repr__(self) -> str:
        return (
            f"<RssStreamProfile(id={self.id}, feed_url={self.feed_url}, "
            f"dw_video_method={self.dw_video_method}, enable_profile={self.enable_profile}, "
            f"created_at={self.created_at}, updated_at={self.updated_at})>"
        )
