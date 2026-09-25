from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.datetime_types import UTCDateTime

if TYPE_CHECKING:
    from backend.db.models import Show
    from backend.db.models.local_media_profile import LocalMediaProfileBase


class CustomIndexState(Base):
    """High-water allocation state for one Show/Local Media Profile/index key."""

    __tablename__ = "custom_index_states"
    __table_args__ = (
        UniqueConstraint(
            "show_id",
            "local_media_profile_id",
            "key",
            name="uq_custom_index_state_scope_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(
        ForeignKey("shows.id", ondelete="CASCADE"),
        index=True,
    )
    local_media_profile_id: Mapped[int] = mapped_column(
        ForeignKey("local_media_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    key: Mapped[str] = mapped_column(String(64))
    next_value: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    show: Mapped["Show"] = relationship()
    local_media_profile: Mapped["LocalMediaProfileBase"] = relationship()
