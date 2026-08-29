from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.types.media_types import MediaType

from .MediaDownloadBase import MediaDownloadBase


class MovieMediaDownload(MediaDownloadBase):
    __tablename__ = "media_downloads_movie"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE.value}

    id: Mapped[int] = mapped_column(
        ForeignKey("media_downloads.id", ondelete="CASCADE"),
        primary_key=True,
    )
