from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column


class MediaContentMetadataMixin:
    """Reusable intrinsic media metadata stored by the content owner.

    MediaItemBase deliberately does not inherit this mixin: a media item models
    WireLoft identity/placement and download state, while the concrete content
    owner decides where these descriptive fields live. Episodes and movies own
    them directly; shared movie-extra sources own them for all of their placements.
    """

    title: Mapped[str] = mapped_column(default="", server_default="")
    description: Mapped[Optional[str]]
    duration: Mapped[float] = mapped_column(default=0.0, server_default="0")
    background_image_path: Mapped[Optional[str]]
    thumbnail_landscape_path: Mapped[Optional[str]]
    thumbnail_portrait_path: Mapped[Optional[str]]
    thumbnail_square_path: Mapped[Optional[str]]
