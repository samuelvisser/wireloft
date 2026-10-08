from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.datetime_types import UTCDateTime


class NotificationChannel(Base):
    """A user-configured Apprise destination. The Apprise URL holds credentials, so it is encrypted."""

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_url: Mapped[str] = mapped_column(Text, nullable=False)
    masked_url: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    # A channel only reports operations that finished after it was (re-)enabled.
    enabled_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_status: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(String(255))
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    consecutive_failures: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )

    routes: Mapped[list["NotificationRoute"]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="NotificationRoute.event",
    )


class NotificationRoute(Base):
    """Sends one WireLoft event to one channel."""

    __tablename__ = "notification_routes"

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="CASCADE"), primary_key=True
    )
    event: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Operations that finished before the route existed are never sent retroactively.
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    channel: Mapped[NotificationChannel] = relationship(back_populates="routes")


class NotificationDelivery(Base):
    """Durable per-channel delivery ledger; an operation is never enqueued twice for a channel."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "operation_id", "channel_id", "operation_finished_at",
            name="uq_notification_delivery_operation_channel",
        ),
        Index("ix_notification_delivery_pending", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_operations.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    operation_finished_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    error: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    channel: Mapped[NotificationChannel] = relationship()
