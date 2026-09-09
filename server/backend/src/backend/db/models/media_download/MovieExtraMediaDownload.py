from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.types.media_types import MediaType

from .MediaDownloadBase import MediaDownloadBase


class MovieExtraMediaDownload(MediaDownloadBase):
    __tablename__ = "media_downloads_movie_extra"
    __mapper_args__ = {"polymorphic_identity": MediaType.MOVIE_EXTRA.value}

    # No extra association key is needed here. MovieExtra itself is the
    # movie-specific placement MediaItem; its source_id points at the globally
    # shared Daily Wire clip identity. Therefore MediaDownloadBase's existing
    # UNIQUE(media_item_id, local_media_profile_id) remains the correct contract.
    id: Mapped[int] = mapped_column(
        ForeignKey("media_downloads.id", ondelete="CASCADE"),
        primary_key=True,
    )
