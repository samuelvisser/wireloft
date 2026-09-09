from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column


class MediaContentMetadataMixin:
    """Reusable intrinsic media metadata stored by the content owner.

    MediaItemBase deliberately does not inherit this mixin: a media item models
    WireLoft identity/placement and download state, while the concrete content
    owner decides where these descriptive fields live. Episodes and movies own
    them directly; shared movie-extra sources own them for all of their placements.
    """

    title: Mapped[str] = mapped_column(
        default="",
        server_default="",
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
    duration: Mapped[float] = mapped_column(
        default=0.0,
        server_default="0",
        nullable=False,
    )
    background_image_path: Mapped[Optional[str]] = mapped_column(nullable=True)
    thumbnail_landscape_path: Mapped[Optional[str]] = mapped_column(nullable=True)
    thumbnail_portrait_path: Mapped[Optional[str]] = mapped_column(nullable=True)
    thumbnail_square_path: Mapped[Optional[str]] = mapped_column(nullable=True)
