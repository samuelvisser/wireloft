"""Apprise notification channels: configuration, event routing and background delivery."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from apprise import LogCapture, NotifyType
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db.core import begin_write_transaction, get_session
from backend.db.models.NotificationChannel import (
    NotificationChannel, NotificationDelivery, NotificationRoute,
)
from backend.db.models.PushNotification import PushDelivery
from backend.security.crypto import decrypt_text, encrypt_text
from backend.services.notification_events import (
    DEFAULT_EVENTS, EVENT_DEFINITIONS, MAX_ALERT_AGE, TERMINAL_STATUSES, EventTone,
    NotificationEvent, NotificationMessage, notification_message, operation_event,
)
from backend.services.notification_services import (
    InvalidDestination, masked_url, parse_destination, service_display_name, service_key_for_url,
)
from task_manager.scheduler.db import TaskOperation

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
ERROR_LIMIT = 200
HISTORY_LIMIT = 100

_NOTIFY_TYPES = {
    EventTone.SUCCESS: NotifyType.SUCCESS,
    EventTone.FAILURE: NotifyType.FAILURE,
    EventTone.INFO: NotifyType.INFO,
    EventTone.NEUTRAL: NotifyType.INFO,
}
_EVENT_TONES = {definition.event: definition.tone for definition in EVENT_DEFINITIONS}
_URL_IN_TEXT = re.compile(r"\S+://\S+")


class ChannelHealth(StrEnum):
    DISABLED = "disabled"
    FAILING = "failing"
    HEALTHY = "healthy"
    UNTESTED = "untested"


class ChannelNotFound(LookupError):
    """No channel exists with the requested id."""


@dataclass(frozen=True)
class ChannelSummary:
    id: int
    name: str
    service: str
    service_name: str
    masked_url: str
    enabled: bool
    health: ChannelHealth
    last_error: str | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    events: tuple[NotificationEvent, ...]


@dataclass(frozen=True)
class TestResult:
    __test__ = False  # Not a pytest test class, despite the name.

    delivered: bool
    error: str | None
    elapsed_ms: int


@dataclass(frozen=True)
class DeliveryRecord:
    id: str
    operation_id: str
    title: str
    event: NotificationEvent
    destination: str
    status: str
    error: str | None
    at: datetime


def _health(channel: NotificationChannel) -> ChannelHealth:
    if not channel.enabled:
        return ChannelHealth.DISABLED
    if channel.consecutive_failures > 0:
        return ChannelHealth.FAILING
    if channel.last_success_at is not None:
        return ChannelHealth.HEALTHY
    return ChannelHealth.UNTESTED


def _summary(channel: NotificationChannel) -> ChannelSummary:
    return ChannelSummary(
        id=channel.id,
        name=channel.name,
        service=channel.service,
        service_name=service_display_name(channel.service),
        masked_url=channel.masked_url,
        enabled=channel.enabled,
        health=_health(channel),
        last_error=channel.last_error,
        last_attempt_at=channel.last_attempt_at,
        last_success_at=channel.last_success_at,
        events=tuple(NotificationEvent(route.event) for route in channel.routes),
    )


def _channel(session: Session, channel_id: int) -> NotificationChannel:
    channel = session.get(NotificationChannel, channel_id)
    if channel is None:
        raise ChannelNotFound(channel_id)
    return channel


def _protected_url(url: str) -> tuple[str, str, str]:
    """Validate a destination and return (encrypted, masked, service key)."""
    normalized = url.strip()
    display = masked_url(normalized)
    encrypted = encrypt_text(normalized)
    if encrypted is None:
        raise RuntimeError("Cannot encrypt the notification destination")
    return encrypted.decode("ascii"), display, service_key_for_url(normalized)


def list_channels() -> list[ChannelSummary]:
    with get_session() as session:
        channels = session.scalars(
            select(NotificationChannel)
            .options(selectinload(NotificationChannel.routes))
            .order_by(NotificationChannel.name)
        ).all()
        return [_summary(channel) for channel in channels]


def create_channel(*, name: str, url: str, events: Iterable[NotificationEvent] = DEFAULT_EVENTS) -> ChannelSummary:
    encrypted, display, service = _protected_url(url)
    now = datetime.now(timezone.utc)
    with get_session() as session:
        begin_write_transaction(session)
        channel = NotificationChannel(
            name=name.strip(), service=service, encrypted_url=encrypted, masked_url=display,
            enabled=True, enabled_at=now, consecutive_failures=0,
            routes=[NotificationRoute(event=event.value, created_at=now) for event in set(events)],
        )
        session.add(channel)
        session.commit()
        session.refresh(channel)
        return _summary(channel)


def update_channel(
    channel_id: int, *, name: str | None = None, enabled: bool | None = None, url: str | None = None,
) -> ChannelSummary:
    protected = _protected_url(url) if url is not None else None
    with get_session() as session:
        begin_write_transaction(session)
        channel = _channel(session, channel_id)
        if name is not None:
            channel.name = name.strip()
        if enabled is not None:
            if enabled and not channel.enabled:
                # Re-enabling must not replay everything that finished while it was off.
                channel.enabled_at = datetime.now(timezone.utc)
            channel.enabled = enabled
        if protected is not None:
            channel.encrypted_url, channel.masked_url, channel.service = protected
            channel.last_status = channel.last_error = None
            channel.consecutive_failures = 0
        session.commit()
        session.refresh(channel)
        return _summary(channel)


def delete_channel(channel_id: int) -> None:
    with get_session() as session:
        begin_write_transaction(session)
        session.delete(_channel(session, channel_id))
        session.commit()


def set_routes(routes: Mapping[int, set[NotificationEvent]]) -> list[ChannelSummary]:
    """Replace the events sent to each given channel in one transaction."""
    now = datetime.now(timezone.utc)
    with get_session() as session:
        begin_write_transaction(session)
        channels = {channel.id: channel for channel in session.scalars(
            select(NotificationChannel)
            .where(NotificationChannel.id.in_(routes))
            .options(selectinload(NotificationChannel.routes))
        )}
        missing = set(routes) - set(channels)
        if missing:
            raise ChannelNotFound(min(missing))
        for channel_id, events in routes.items():
            channel = channels[channel_id]
            wanted = {event.value for event in events}
            # Keep a route's original timestamp so unchanged routes never replay old operations.
            channel.routes = [route for route in channel.routes if route.event in wanted] + [
                NotificationRoute(event=event, created_at=now)
                for event in sorted(wanted - {route.event for route in channel.routes})
            ]
        session.commit()
        return [_summary(channel) for channel in session.scalars(
            select(NotificationChannel)
            .options(selectinload(NotificationChannel.routes))
            .order_by(NotificationChannel.name)
        )]


def _error_summary(log: str, url: str) -> str:
    lines = [line.strip() for line in log.splitlines() if line.strip()]
    text = lines[-1] if lines else "The service did not accept the notification"
    text = text.replace(url, "[destination]")
    return _URL_IN_TEXT.sub("[address]", text)[:ERROR_LIMIT]


def _send(url: str, *, title: str, body: str, notify_type: NotifyType) -> tuple[bool, str | None]:
    try:
        plugin = parse_destination(url)
    except InvalidDestination as error:
        return False, str(error)[:ERROR_LIMIT]
    try:
        with LogCapture(level=logging.WARNING) as capture:
            delivered = plugin.notify(body=body, title=title, notify_type=notify_type)
            log = capture.getvalue()
    except Exception as error:  # Apprise plugins talk to arbitrary services.
        logger.warning("Notification plugin raised %s", type(error).__name__)
        return False, f"The service could not be reached ({type(error).__name__})"
    return (True, None) if delivered else (False, _error_summary(log, url))


def _record_attempt(channel: NotificationChannel, *, delivered: bool, error: str | None) -> None:
    now = datetime.now(timezone.utc)
    channel.last_attempt_at = now
    if delivered:
        channel.last_status, channel.last_error = "SENT", None
        channel.last_success_at = now
        channel.consecutive_failures = 0
    else:
        channel.last_status, channel.last_error = "FAILED", error
        channel.consecutive_failures += 1


def send_test(url: str) -> TestResult:
    """Send a test message to a destination that has not been saved yet."""
    started = time.monotonic()
    delivered, error = _send(
        url, title="WireLoft test notification",
        body="If you can read this, WireLoft can reach this destination.", notify_type=NotifyType.INFO,
    )
    return TestResult(delivered, error, round((time.monotonic() - started) * 1000))


def send_test_to_channel(channel_id: int) -> TestResult:
    with get_session() as session:
        channel = _channel(session, channel_id)
        decrypted = decrypt_text(channel.encrypted_url)
    if decrypted is None:
        return TestResult(False, "WireLoft cannot decrypt this destination. Enter it again.", 0)
    result = send_test(decrypted)
    with get_session() as session:
        begin_write_transaction(session)
        stored = session.get(NotificationChannel, channel_id)
        if stored is not None:
            _record_attempt(stored, delivered=result.delivered, error=result.error)
        session.commit()
    return result


def _enqueue_pending(session: Session, now: datetime) -> None:
    channels = list(session.scalars(
        select(NotificationChannel)
        .where(NotificationChannel.enabled.is_(True))
        .options(selectinload(NotificationChannel.routes))
    ))
    routed = [channel for channel in channels if channel.routes]
    if not routed:
        return
    earliest = max(min(c.enabled_at for c in routed), now - MAX_ALERT_AGE)
    operations = list(session.scalars(select(TaskOperation).where(
        TaskOperation.status.in_(TERMINAL_STATUSES),
        TaskOperation.finished_at >= earliest,
        TaskOperation.finished_at <= now,
    ).order_by(TaskOperation.finished_at.desc()).limit(100)))
    if not operations:
        return
    existing = set(session.execute(select(
        NotificationDelivery.operation_id, NotificationDelivery.channel_id,
        NotificationDelivery.operation_finished_at,
    ).where(NotificationDelivery.operation_id.in_([op.id for op in operations]))).all())
    for operation in operations:
        event = operation_event(operation)
        for channel in routed:
            route = next((r for r in channel.routes if r.event == event.value), None)
            if (
                route is None
                or operation.finished_at < max(channel.enabled_at, route.created_at)
                or (operation.id, channel.id, operation.finished_at) in existing
            ):
                continue
            session.add(NotificationDelivery(
                operation_id=operation.id, channel_id=channel.id, event=event.value,
                operation_finished_at=operation.finished_at, status="PENDING",
                attempts=0, next_attempt_at=now,
            ))


def _reserve(delivery_id: int, now: datetime) -> tuple[str, NotificationMessage] | None:
    """Validate a due delivery in a short write transaction; return what to send."""
    with get_session() as session:
        begin_write_transaction(session)
        delivery = session.get(NotificationDelivery, delivery_id)
        if delivery is None or delivery.status != "PENDING":
            session.commit()
            return None
        channel = session.get(NotificationChannel, delivery.channel_id)
        operation = session.get(TaskOperation, delivery.operation_id)
        if channel is None or operation is None:
            session.delete(delivery)
            session.commit()
            return None
        route_exists = any(route.event == delivery.event for route in channel.routes)
        if (
            not channel.enabled or not route_exists
            or operation.status not in TERMINAL_STATUSES
            or operation.finished_at != delivery.operation_finished_at
            or operation.finished_at < now - MAX_ALERT_AGE
        ):
            delivery.status = "CANCELED"
            session.commit()
            return None
        decrypted = decrypt_text(channel.encrypted_url)
        if decrypted is None:
            logger.warning("Cannot decrypt notification channel %s; disabling it", channel.id)
            channel.enabled = False
            delivery.status = "CANCELED"
            _record_attempt(channel, delivered=False, error="WireLoft cannot decrypt this destination. Enter it again.")
            session.commit()
            return None
        message = notification_message(operation)
        session.commit()
        return decrypted, message


def _record_result(delivery_id: int, *, delivered: bool, error: str | None) -> None:
    with get_session() as session:
        begin_write_transaction(session)
        delivery = session.get(NotificationDelivery, delivery_id)
        if delivery is None or delivery.status != "PENDING":
            session.commit()
            return
        channel = session.get(NotificationChannel, delivery.channel_id)
        delivery.attempts += 1
        if channel is not None:
            _record_attempt(channel, delivered=delivered, error=error)
        if delivered:
            delivery.status, delivery.error = "SENT", None
            delivery.sent_at = datetime.now(timezone.utc)
        else:
            delivery.error = error
            if delivery.attempts < MAX_ATTEMPTS:
                delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=min(600, 15 * 2 ** (delivery.attempts - 1))
                )
            else:
                delivery.status = "FAILED"
                logger.warning("Giving up on notification delivery %s after %s attempts", delivery_id, delivery.attempts)
        session.commit()


def deliver_pending_channel_notifications() -> None:
    """One bounded background pass; nothing in an API request waits for an external service."""
    with get_session() as session:
        has_channels = session.scalar(select(NotificationChannel.id).where(
            NotificationChannel.enabled.is_(True)
        ).limit(1)) is not None
    if not has_channels:
        return

    now = datetime.now(timezone.utc)
    with get_session() as session:
        begin_write_transaction(session)
        _enqueue_pending(session, now)
        session.commit()

    with get_session() as session:
        due = list(session.scalars(select(NotificationDelivery.id).where(
            NotificationDelivery.status == "PENDING",
            NotificationDelivery.next_attempt_at <= now,
        ).order_by(NotificationDelivery.id).limit(30)))

    for delivery_id in due:
        reserved = _reserve(delivery_id, now)
        if reserved is None:
            continue
        url, message = reserved
        # Never hold an SQLite transaction while waiting on an external service.
        delivered, error = _send(
            url, title=message.title, body=message.body,
            notify_type=_NOTIFY_TYPES[_EVENT_TONES[message.event]],
        )
        _record_result(delivery_id, delivered=delivered, error=error)


def delivery_history(limit: int = 50) -> list[DeliveryRecord]:
    """Recent per-destination results, across Apprise channels and Web Push devices."""
    limit = max(1, min(limit, HISTORY_LIMIT))
    with get_session() as session:
        channel_rows = session.execute(
            select(NotificationDelivery, NotificationChannel.name, TaskOperation.title)
            .join(NotificationChannel, NotificationChannel.id == NotificationDelivery.channel_id)
            .join(TaskOperation, TaskOperation.id == NotificationDelivery.operation_id)
            .where(NotificationDelivery.status.in_(("SENT", "FAILED")))
            .order_by(NotificationDelivery.id.desc()).limit(limit)
        ).all()
        push_rows = session.execute(
            select(PushDelivery, TaskOperation)
            .join(TaskOperation, TaskOperation.id == PushDelivery.operation_id)
            .where(PushDelivery.status.in_(("SENT", "FAILED")))
            .order_by(PushDelivery.id.desc()).limit(limit)
        ).all()
        records = [
            DeliveryRecord(
                id=f"channel-{delivery.id}", operation_id=delivery.operation_id, title=title,
                event=NotificationEvent(delivery.event), destination=name, status=delivery.status,
                error=delivery.error, at=delivery.sent_at or delivery.created_at,
            )
            for delivery, name, title in channel_rows
        ] + [
            DeliveryRecord(
                id=f"push-{delivery.id}", operation_id=operation.id, title=operation.title,
                event=operation_event(operation), destination="Web Push", status=delivery.status,
                error=None, at=delivery.sent_at or delivery.created_at,
            )
            for delivery, operation in push_rows
        ]
    return sorted(records, key=lambda record: record.at, reverse=True)[:limit]
