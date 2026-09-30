from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from .MediaDownloadBase import MediaDownloadBase


class MediaDownloadAsset(Base):
    """A published auxiliary file owned by a media/profile artifact.

    Acquisition policy belongs to the immutable attempt plan. Only published
    file facts live here, so adding subtitles does not need another path column.
    """
    __tablename__ = "media_download_assets"
    __table_args__ = (UniqueConstraint("media_download_id", "asset_key", name="uq_download_asset_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    media_download_id: Mapped[int] = mapped_column(ForeignKey("media_downloads.id", ondelete="CASCADE"), index=True)
    asset_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40))
    path: Mapped[str]
    suffix: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    media_download: Mapped["MediaDownloadBase"] = relationship(back_populates="assets")
