from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.StreamWorkerBase import StreamWorkerBase
from backend.types.stream_worker_types import StreamWorkerType


class RssStreamWorker(StreamWorkerBase):
    __tablename__ = "rss_stream_workers"
    __mapper_args__ = {"polymorphic_identity": StreamWorkerType.RSS.value}

    # Columns
    id: Mapped[int] = mapped_column(ForeignKey("stream_workers.id", ondelete="CASCADE"), primary_key=True)
    feed_url: Mapped[str]


    def __repr__(self) -> str:
        return f"<RssStreamWorker(id={self.id}, feed_url={self.feed_url}, created_at={self.created_at}, updated_at={self.updated_at})>"