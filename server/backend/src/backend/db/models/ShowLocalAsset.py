from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.db.datetime_types import UTCDateTime


class ShowLocalAsset(Base):
    """One profile's ownership of artwork, including old roots awaiting a rename.

    Several profiles may reference the same physical file for the same show.
    Hashes ensure externally supplied or edited artwork is never overwritten.
    The pending hash makes a crash between publication and commit recoverable.
    """
    __tablename__ = "show_local_assets"
    __table_args__ = (
        UniqueConstraint("show_id", "local_media_profile_id", "asset_type", "file_path", name="uq_show_local_asset_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id", ondelete="CASCADE"), index=True)
    local_media_profile_id: Mapped[int] = mapped_column(ForeignKey("local_media_profiles.id", ondelete="CASCADE"), index=True)
    asset_type: Mapped[str] = mapped_column(String(16))
    file_path: Mapped[str]
    source_url: Mapped[str | None]
    content_hash: Mapped[str | None] = mapped_column(String(64))
    pending_hash: Mapped[str | None] = mapped_column(String(64))
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
