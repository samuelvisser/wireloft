from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.types.local_media_profile_types import LocalMediaProfileType

from .LocalMediaProfileBase import LocalMediaProfileBase


class MovieLocalMediaProfile(LocalMediaProfileBase):
    __tablename__ = "local_media_profiles_movie"
    __mapper_args__ = {"polymorphic_identity": LocalMediaProfileType.MOVIE.value}

    id: Mapped[int] = mapped_column(
        ForeignKey("local_media_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
