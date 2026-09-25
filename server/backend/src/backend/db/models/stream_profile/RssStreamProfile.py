from sqlalchemy import ForeignKey, JSON
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from .StreamProfileBase import StreamProfileBase
from backend.types.stream_profile_types import StreamProfileType


class RssStreamProfile(StreamProfileBase):
    __tablename__ = "stream_profiles_rss"
    __mapper_args__ = {"polymorphic_identity": StreamProfileType.RSS.value}

    id: Mapped[int] = mapped_column(
        ForeignKey("stream_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    feed_url: Mapped[str]
    video_output_mode: Mapped[str | None] = mapped_column(nullable=True)
    max_items: Mapped[int] = mapped_column(default=0)
    stream_live_episodes: Mapped[bool] = mapped_column(
        default=False,
        server_default="0",
        nullable=False,
    )
    live_episode_handoff_ids: Mapped[list[int]] = mapped_column(
        MutableList.as_mutable(JSON),
        default=list,
        server_default="[]",
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<RssStreamProfile(id={self.id}, feed_url={self.feed_url}, "
            f"video_output_mode={self.video_output_mode}, max_items={self.max_items}, "
            f"stream_live_episodes={self.stream_live_episodes}, "
            f"enable_profile={self.enable_profile}, created_at={self.created_at}, "
            f"updated_at={self.updated_at})>"
        )
