from datetime import datetime

from sqlalchemy import DateTime, func, String, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base

class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # OAuth/DailyWire auth metadata
    auth_issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Encrypted tokens (Fernet, base64) stored as bytes
    encrypted_access_token: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # Token and auth status
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_auth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )