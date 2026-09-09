from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.db.datetime_types import UTCDateTime


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    # Alembic normally stores this value in a dedicated alembic_version table.
    # WireLoft's migration runner maps Alembic's logical ``version_num`` field to
    # this clearer physical column instead.
    alembic_version_num: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return (
            f"<Settings(id={self.id}, onboarding_completed={self.onboarding_completed}, "
            f"alembic_version_num={self.alembic_version_num}, "
            f"created_at={self.created_at}, updated_at={self.updated_at})>"
        )
