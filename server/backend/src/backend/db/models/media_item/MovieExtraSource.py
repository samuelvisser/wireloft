from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.mixins.MediaContentMetadataMixin import MediaContentMetadataMixin

if TYPE_CHECKING:
    from .MovieExtra import MovieExtra


class MovieExtraSource(MediaContentMetadataMixin, Base):
    """Canonical metadata for one Daily Wire movie-extra clip.

    The reusable content metadata mixin is stored here because the clip itself,
    not any one parent-specific MovieExtra placement, owns those values.
    """

    __tablename__ = "movie_extra_sources"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_movie_extra_sources_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(nullable=False)
    sharing_url: Mapped[Optional[str]]
    published_date: Mapped[Optional[datetime]]
    available_for: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )

    movie_extras: Mapped[list["MovieExtra"]] = relationship(back_populates="source")

    def update_metadata(self, values: Mapping[str, Any]) -> None:
        """Apply authoritative source metadata that an upstream response supplied.

        Missing keys are left unchanged. Values that are present are retained as
        returned, including explicit empty values. Fields that do not belong to
        ``MovieExtraSource`` (for example playback tokens) are ignored.
        """
        incoming_slug = values.get("slug")
        if incoming_slug is not None and incoming_slug != self.slug:
            raise ValueError("MovieExtraSource metadata can only be updated for the same slug")

        for column in self.__table__.columns:
            field = column.key
            if field in {"id", "slug"} or field not in values:
                continue
            setattr(self, field, values[field])

    def merge_metadata(self, other: "MovieExtraSource") -> None:
        """Merge useful metadata from another representation of this source.

        Daily Wire can expose the same clip beneath multiple movies, with one
        parent omitting metadata that another provides. Empty values therefore do
        not erase richer values already stored for the shared source.
        """
        if self.slug != other.slug:
            raise ValueError("MovieExtraSource metadata can only be merged for the same slug")

        for column in self.__table__.columns:
            field = column.key
            if field in {"id", "slug"}:
                continue

            value = getattr(other, field)
            if value is None:
                continue
            if isinstance(value, (str, list, dict)) and not value:
                continue
            if field == "duration" and value <= 0:
                continue
            setattr(self, field, value)

    def __repr__(self) -> str:
        return (
            f"<MovieExtraSource(id={self.id}, slug={self.slug!r}, title={self.title!r})>"
        )
