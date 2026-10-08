from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.db.datetime_types import UTCDateTime


class PushVapidKey(Base):
    """One installation-scoped VAPID signing identity, encrypted with WireLoft's secret."""

    __tablename__ = "push_vapid_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    encrypted_private_key: Mapped[str] = mapped_column(Text, nullable=False)


class PushSubscription(Base):
    """An explicitly opted-in browser/device. Endpoint and key material are encrypted."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    encrypted_subscription: Mapped[str] = mapped_column(Text, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    enabled_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )


class PushDelivery(Base):
    """Durable per-device delivery ledger; one operation cannot be enqueued twice."""

    __tablename__ = "push_deliveries"
    __table_args__ = (
        UniqueConstraint("operation_id", "subscription_id", "operation_finished_at", name="uq_push_delivery_operation_device"),
        Index("ix_push_delivery_pending", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_operations.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    operation_finished_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
