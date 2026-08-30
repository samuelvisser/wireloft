from datetime import datetime

from sqlalchemy import Boolean, DateTime, false, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return (
            f"<Settings(id={self.id}, onboarding_completed={self.onboarding_completed}, "
            f"created_at={self.created_at}, updated_at={self.updated_at})>"
        )
