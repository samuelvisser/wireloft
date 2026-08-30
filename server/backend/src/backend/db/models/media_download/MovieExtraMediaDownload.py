from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.types.media_types import MediaType

from .MediaDownloadBase import MediaDownloadBase


class MovieExtraMediaDownload(MediaDownloadBase):
    __tablename__ = "media_downloads_movie_extra"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE_EXTRA.value}

    id: Mapped[int] = mapped_column(
        ForeignKey("media_downloads.id", ondelete="CASCADE"),
        primary_key=True,
    )
