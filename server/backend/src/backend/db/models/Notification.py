"""Messages and actions: where they go, the rules that say what goes where, and what was sent.

A destination is an Apprise service, a media server to refresh, a webhook or a script. Push to the installed app
is built in and needs no destination. Rules are the sentences on Settings › Messages and actions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.db.datetime_types import UTCDateTime


class NotificationDestination(Base):
    """Somewhere a rule can send a message or do something. Its settings hold credentials, so they are encrypted."""

    __tablename__ = "notification_destinations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), comment="apprise, jellyfin, emby, plex, webhook or script")
    name: Mapped[str] = mapped_column(String(80), unique=True)
    service: Mapped[str] = mapped_column(String(64), comment="The Apprise service key, or the kind")
    encrypted_config: Mapped[str] = mapped_column(Text, comment="The destination's settings as encrypted JSON")
    masked: Mapped[str] = mapped_column(String(255), comment="The destination, safe to show")
    enabled: Mapped[bool] = mapped_column(default=True)
    last_status: Mapped[Optional[str]] = mapped_column(String(16))
    last_error: Mapped[Optional[str]] = mapped_column(String(255))
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    last_success_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), onupdate=func.now())


class NotificationRule(Base):
    """One sentence: when something happens in which shows, send it where, and how."""

    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position: Mapped[int] = mapped_column(default=0)
    default_key: Mapped[Optional[str]] = mapped_column(String(32), comment="Which default rule this is, if any")
    enabled: Mapped[bool] = mapped_column(default=True)
    event: Mapped[str] = mapped_column(String(32))
    show_scope: Mapped[str] = mapped_column(String(16), default="any", comment="any or chosen")
    show_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    push: Mapped[bool] = mapped_column(default=False, comment="Push to every device that turned push on")
    destination_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    delivery: Mapped[str] = mapped_column(String(16), default="now", comment="now, grouped (per show) or daily")
    summary_time: Mapped[str] = mapped_column(String(5), default="08:00", comment="When a daily summary goes out")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())


class NotificationEvent(Base):
    """Something that happened, as messages and actions see it."""

    __tablename__ = "notification_events"
    __table_args__ = (Index("ix_notification_events_dedupe", "dedupe_key", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(32), index=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    show_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shows.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[Optional[str]] = mapped_column(String(512), comment="The page in WireLoft it is about")
    data: Mapped[dict] = mapped_column(JSON, default=dict, comment="Details for actions, such as the file's folder")
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(255), comment="The same problem is sent again only after a day")


class NotificationDelivery(Base):
    """One event on its way to one destination or device, and what happened."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (Index("ix_notification_deliveries_pending", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("notification_events.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notification_rules.id", ondelete="SET NULL"))
    destination_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notification_destinations.id", ondelete="CASCADE"))
    subscription_id: Mapped[Optional[int]] = mapped_column(ForeignKey("push_subscriptions.id", ondelete="CASCADE"))
    group_key: Mapped[Optional[str]] = mapped_column(String(128), comment="Deliveries with the same key go out as one message")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", comment="PENDING, SENT, FAILED or CANCELED")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime())
    error: Mapped[Optional[str]] = mapped_column(String(255))
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    event: Mapped[NotificationEvent] = relationship()
    destination: Mapped[Optional[NotificationDestination]] = relationship()


class PushVapidKey(Base):
    """The installation's one Web Push signing key, encrypted."""

    __tablename__ = "push_vapid_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    encrypted_private_key: Mapped[str] = mapped_column(Text)


class PushSubscription(Base):
    """A browser or phone that asked for push messages. Its endpoint and keys are encrypted."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64), unique=True)
    encrypted_subscription: Mapped[str] = mapped_column(Text)
    device_name: Mapped[str] = mapped_column(String(80), default="This device")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
