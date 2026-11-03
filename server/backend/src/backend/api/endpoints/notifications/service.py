"""Messages and actions for the API: destinations, rules, push devices and history."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.models.notifications import (
    DestinationCreate,
    DestinationInput,
    DestinationUpdate,
    PushSubscriptionInput,
    RuleInput,
)
from backend.db.models import (
    NotificationDelivery,
    NotificationDestination,
    NotificationEvent,
    NotificationRule,
    PushSubscription,
)
from backend.services.notifications import DEFINITIONS, Event
from backend.services.notifications.apprise_services import InvalidDestination, build_url, service_catalog
from backend.services.notifications.destinations import (
    DestinationNotFound,
    Kind,
    check_config,
    config_of,
    create_destination,
    delete_destination,
    display_service,
    get_destination,
    health,
    list_destinations,
    purpose,
    record_attempt,
    update_destination,
)
from backend.services.notifications.errors import NotificationError
from backend.services.notifications.push import PushRejected, find_subscription, save_subscription, vapid_public_key
from backend.services.notifications.rules import (
    RuleNotFound,
    RuleValues,
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    restore_default_rules,
    update_rule,
)
from backend.services.notifications.senders import test_destination, webhook_payload

_HISTORY_LIMIT = 200
# Settings that are not secret, shown again when a destination is edited.
_SHOWN_SETTINGS = ("address", "scope", "path_from", "path_to", "url", "method", "secret_header", "script", "timeout_seconds")


# ---------- Destinations ----------
def _config(destination: DestinationInput) -> dict[str, Any]:
    """The settings as the destination service stores them."""
    if destination.kind == Kind.APPRISE:
        apprise = destination.apprise
        try:
            url = build_url(apprise.service, apprise.values) if apprise.mode == "fields" else apprise.url
        except InvalidDestination as error:
            raise NotificationError(str(error), field="destination") from None
        return {"url": url}
    part = {
        Kind.WEBHOOK: destination.webhook, Kind.SCRIPT: destination.script,
    }.get(destination.kind, destination.media_server)
    return part.model_dump()


def _checked(call):
    try:
        return call()
    except InvalidDestination as error:
        raise NotificationError(str(error), field="destination") from None


@dataclass(frozen=True)
class DestinationSource:
    """A destination as the API shows it."""

    id: int
    kind: str
    purpose: str
    name: str
    service: str
    service_name: str
    masked: str
    enabled: bool
    health: str
    last_error: str | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    settings: dict[str, Any]


def _shown(destination: NotificationDestination) -> DestinationSource:
    config = config_of(destination) or {}
    if destination.kind == Kind.APPRISE:
        config = {}
    return DestinationSource(
        id=destination.id, kind=destination.kind, purpose=purpose(destination.kind), name=destination.name,
        service=destination.service, service_name=display_service(destination), masked=destination.masked,
        enabled=destination.enabled, health=health(destination).value, last_error=destination.last_error,
        last_attempt_at=destination.last_attempt_at, last_success_at=destination.last_success_at,
        settings={key: value for key, value in config.items() if key in _SHOWN_SETTINGS},
    )


def _name_free(s: Session, name: str, *, except_id: int | None = None) -> None:
    existing = s.scalar(select(NotificationDestination.id).where(NotificationDestination.name == name.strip()))
    if existing is not None and existing != except_id:
        raise NotificationError("Another destination already has this name", field="name")


def destinations(s: Session) -> list[DestinationSource]:
    return [_shown(destination) for destination in list_destinations(s)]


def preview(body: DestinationInput) -> dict[str, str]:
    checked = _checked(lambda: check_config(Kind(body.kind), _config(body)))
    service_name = display_service(NotificationDestination(kind=str(body.kind), service=checked.service))
    return {"service": checked.service, "service_name": service_name, "masked": checked.masked}


def add_destination(s: Session, body: DestinationCreate) -> DestinationSource:
    _name_free(s, body.name)
    destination = _checked(lambda: create_destination(
        s, kind=Kind(body.destination.kind), name=body.name, config=_config(body.destination),
    ))
    s.commit()
    return _shown(destination)


def _found(call):
    try:
        return call()
    except (DestinationNotFound, RuleNotFound):
        raise NotificationError("It no longer exists", status_code=404) from None


def change_destination(s: Session, destination_id: int, body: DestinationUpdate) -> DestinationSource:
    current = _found(lambda: get_destination(s, destination_id))
    if body.name is not None:
        _name_free(s, body.name, except_id=destination_id)
    if body.destination is not None and str(body.destination.kind) != current.kind:
        raise NotificationError("A destination keeps its kind. Add a new one instead", field="destination")
    config = _config(body.destination) if body.destination is not None else None
    destination = _checked(lambda: update_destination(
        s, destination_id, name=body.name, enabled=body.enabled, config=config,
    ))
    s.commit()
    return _shown(destination)


def remove_destination(s: Session, destination_id: int) -> None:
    _found(lambda: delete_destination(s, destination_id))
    s.commit()


def _sample(s: Session) -> NotificationEvent | None:
    """The newest download, so a script or webhook test gets real values."""
    return s.scalar(
        select(NotificationEvent).where(NotificationEvent.event == Event.EPISODE_DOWNLOADED.value)
        .order_by(NotificationEvent.id.desc()).limit(1)
    )


def _timed_test(kind: Kind, config: dict[str, Any], sample: NotificationEvent | None) -> dict[str, Any]:
    started = time.monotonic()
    outcome = test_destination(kind, config, sample)
    return {"delivered": outcome.delivered, "error": outcome.error, "elapsed_ms": int((time.monotonic() - started) * 1000)}


def test_unsaved(s: Session, body: DestinationInput) -> dict[str, Any]:
    checked = _checked(lambda: check_config(Kind(body.kind), _config(body)))
    return _timed_test(Kind(body.kind), checked.config, _sample(s))


def test_saved(s: Session, destination_id: int) -> dict[str, Any]:
    destination = _found(lambda: get_destination(s, destination_id))
    config = config_of(destination)
    if config is None:
        raise NotificationError("WireLoft cannot read this destination's settings. Enter them again", field="destination")
    result = _timed_test(Kind(destination.kind), config, _sample(s))
    record_attempt(destination, delivered=result["delivered"], error=result["error"])
    s.commit()
    return result


def services() -> list:
    return list(service_catalog())


def webhook_example(s: Session) -> dict[str, Any]:
    sample = _sample(s) or NotificationEvent(
        event=Event.EPISODE_DOWNLOADED.value, title="Episode downloaded: An example episode",
        body="The Example Show", occurred_at=datetime.now(timezone.utc), url="/show/example/episode/example",
        data={"show": "The Example Show", "episode": "An example episode",
              "filePath": "/downloads/The Example Show/An example episode.mp4", "folder": "/downloads/The Example Show"},
    )
    return {"payload": webhook_payload(sample)}


# ---------- Rules ----------
def _values(s: Session, body: RuleInput) -> RuleValues:
    definition = DEFINITIONS[Event(body.event)]
    if not definition.shows and body.show_scope != "any":
        raise NotificationError("This does not belong to a show", field="showScope")
    known = {destination.id: destination for destination in list_destinations(s)}
    missing = [value for value in body.destination_ids if value not in known]
    if missing:
        raise NotificationError("A chosen destination no longer exists", field="destinationIds")
    if not definition.actions and any(purpose(known[value].kind) == "action" for value in body.destination_ids):
        raise NotificationError("Actions only run on downloads", field="destinationIds")
    if not body.push and not body.destination_ids and body.enabled:
        raise NotificationError("Choose where it goes", field="destinationIds")
    return RuleValues(
        enabled=body.enabled, event=Event(body.event), show_scope=body.show_scope, show_ids=body.show_ids,
        push=body.push, destination_ids=body.destination_ids, delivery=body.delivery, summary_time=body.summary_time,
    )


def rules(s: Session) -> list[NotificationRule]:
    return list_rules(s)


def add_rule(s: Session, body: RuleInput) -> NotificationRule:
    rule = create_rule(s, _values(s, body))
    s.commit()
    return rule


def change_rule(s: Session, rule_id: int, body: RuleInput) -> NotificationRule:
    rule = _found(lambda: get_rule(s, rule_id))
    update_rule(s, rule, _values(s, body))
    s.commit()
    return rule


def remove_rule(s: Session, rule_id: int) -> None:
    rule = _found(lambda: get_rule(s, rule_id))
    delete_rule(s, rule)
    s.commit()


def restore_defaults(s: Session) -> list[NotificationRule]:
    restore_default_rules(s)
    s.commit()
    return list_rules(s)


# ---------- History ----------
@dataclass(frozen=True)
class DeliverySource:
    id: int
    title: str
    event: str
    destination: str
    status: str
    error: str | None
    at: datetime
    retry_at: datetime | None = None
    """When a failed attempt is tried again."""


def _deliveries(s: Session, query) -> list[DeliverySource]:
    rows = s.scalars(query.order_by(NotificationDelivery.id.desc()).limit(_HISTORY_LIMIT)).all()
    devices = {device.id: device.device_name for device in s.scalars(select(PushSubscription))}
    return [
        DeliverySource(
            id=row.id, title=row.event.title, event=row.event.event,
            destination=row.destination.name if row.destination is not None
            else f"Push to {devices.get(row.subscription_id, 'a device')}",
            status=row.status, error=row.error, at=row.sent_at or row.created_at or row.next_attempt_at,
            retry_at=row.next_attempt_at if row.status == "PENDING" and row.attempts else None,
        )
        for row in rows
    ]


def history(s: Session) -> list[DeliverySource]:
    return _deliveries(s, select(NotificationDelivery))


# ---------- Devices ----------
def devices(s: Session) -> list[PushSubscription]:
    return list(s.scalars(select(PushSubscription).order_by(PushSubscription.created_at.desc())))


def remove_device(s: Session, device_id: int) -> None:
    device = s.get(PushSubscription, device_id)
    if device is None:
        raise NotificationError("This device is no longer registered", status_code=404)
    s.delete(device)
    s.commit()


# ---------- Push ----------
def push_key(s: Session) -> dict[str, str]:
    key = vapid_public_key(s)
    s.commit()
    return {"public_key": key}


def subscribe(s: Session, body: PushSubscriptionInput) -> PushSubscription:
    try:
        device = save_subscription(
            s, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth,
            device_name=body.device_name,
        )
    except PushRejected as error:
        raise NotificationError(str(error), field="endpoint") from None
    s.commit()
    return device


def lookup(s: Session, endpoint: str) -> dict[str, Any]:
    device = find_subscription(s, endpoint)
    if device is None:
        return {"subscribed": False}
    return {"subscribed": True, "device_id": device.id}


def unsubscribe(s: Session, endpoint: str) -> None:
    device = find_subscription(s, endpoint)
    if device is not None:
        s.delete(device)
        s.commit()


def push_test(s: Session, endpoint: str) -> None:
    """Send a test push to this device through the normal queue."""
    device = find_subscription(s, endpoint)
    if device is None:
        raise NotificationError("Turn on notifications on this device first", field="endpoint")
    event = NotificationEvent(
        event="test", occurred_at=datetime.now(timezone.utc), title="WireLoft test notification",
        body="Notifications work on this device.", url="/settings?tab=notifications", data={},
    )
    s.add(event)
    s.flush()
    s.add(NotificationDelivery(
        event_id=event.id, subscription_id=device.id, status="PENDING",
        next_attempt_at=datetime.now(timezone.utc),
    ))
    s.commit()

