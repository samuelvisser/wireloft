from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.types.media_types import MediaType

from .MediaDownloadBase import MediaDownloadBase


class TrailerMediaDownload(MediaDownloadBase):
    __tablename__ = "media_downloads_trailer"
    __mapper_args__ = {"polymorphic_identity": MediaType.TRAILER.value}

    id: Mapped[int] = mapped_column(
        ForeignKey("media_downloads.id", ondelete="CASCADE"),
        primary_key=True,
    )
