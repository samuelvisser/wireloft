"""Which rules want an event, and sending what is due in the background.

Nothing in an API request or a download waits for an outside service: ``emit`` only stores deliveries, and a
background thread sends them a few seconds later. New downloads of one show that arrive close together
go out as one message, the same problem is sent again only after a day, and a daily summary waits for its time.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.db.models import NotificationDelivery, NotificationDestination, NotificationRule, PushSubscription
from backend.db.models import NotificationEvent as EventRow

from .destinations import ACTION_KINDS, MEDIA_SERVERS, Kind, config_of, record_attempt
from .events import DEFINITIONS, Event, emit
from .push import send_push, vapid_key
from .senders import Outcome, call_webhook, refresh_media_server, run_script, send_message, tone_of, webhook_payload

logger = logging.getLogger(__name__)

REPEAT_AFTER = timedelta(days=1)
"""The same problem, for the same rule, is sent again only after this long."""
DOWNLOAD_GROUPING = timedelta(minutes=1)
"""New downloads of one show within this long of each other go out as one message."""
GROUPED_WINDOW = timedelta(hours=1)
"""A rule that groups per show collects this long before sending."""
REFRESH_GROUPING = timedelta(minutes=1)
"""Media server refreshes are batched over this long, so 40 downloads in a row are one refresh."""
MAX_ATTEMPTS = 5
WEBHOOK_RETRY_SECONDS = (30, 60, 120)
"""A webhook is tried again three times over a few minutes before it counts as failed."""
_DUE_PER_PASS = 200
_TITLES_IN_A_MESSAGE = 10
_BATCHED_EVENTS = frozenset({Event.EPISODE_DOWNLOADED, Event.EPISODE_REPLACED, Event.NEW_EPISODES})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def next_summary_at(summary_time: str, now: datetime) -> datetime:
    """The next time a daily summary set to ``HH:MM`` (this machine's time zone) goes out."""
    hours, minutes = (int(part) for part in summary_time.split(":"))
    local = now.astimezone()
    at = datetime.combine(local.date(), time(hours, minutes), tzinfo=local.tzinfo)
    if at <= local:
        at += timedelta(days=1)
    return at.astimezone(timezone.utc)


def _rule_wants(session: Session, rule: NotificationRule, event: EventRow) -> bool:
    definition = DEFINITIONS.get(Event(event.event))
    if definition is None:
        return False
    if rule.event == Event.EVERYTHING:
        if rule.delivery != "daily":
            return False
    elif rule.event != event.event:
        return False
    if not definition.shows or event.show_id is None:
        return True
    return rule.show_scope != "chosen" or event.show_id in (rule.show_ids or [])


def _repeated(session: Session, rule: NotificationRule, event: EventRow) -> bool:
    if not event.dedupe_key:
        return False
    return session.scalar(
        select(NotificationDelivery.id)
        .join(EventRow, EventRow.id == NotificationDelivery.event_id)
        .where(
            NotificationDelivery.rule_id == rule.id,
            NotificationDelivery.status != "CANCELED",
            EventRow.dedupe_key == event.dedupe_key,
            EventRow.id != event.id,
            EventRow.occurred_at > event.occurred_at - REPEAT_AFTER,
        )
        .limit(1)
    ) is not None


def _push_targets(session: Session) -> list[PushSubscription]:
    """Every device that turned push on."""
    return list(session.scalars(select(PushSubscription)))


def enqueue(session: Session, event: EventRow) -> None:
    """Add a delivery for every destination and device each matching rule sends this event to."""
    now = event.occurred_at
    rules = session.scalars(
        select(NotificationRule).where(
            NotificationRule.enabled.is_(True),
            or_(NotificationRule.event == event.event, NotificationRule.event == Event.EVERYTHING.value),
        ).order_by(NotificationRule.position, NotificationRule.id)
    )
    definition = DEFINITIONS[Event(event.event)]
    for rule in rules:
        if not _rule_wants(session, rule, event) or _repeated(session, rule, event):
            continue
        if rule.delivery == "daily":
            at, group = next_summary_at(rule.summary_time, now), f"daily:{rule.id}"
        elif rule.delivery == "grouped" and event.show_id is not None:
            at, group = now + GROUPED_WINDOW, f"show:{rule.id}:{event.show_id}:{event.event}"
        elif Event(event.event) in _BATCHED_EVENTS and event.show_id is not None:
            at, group = now + DOWNLOAD_GROUPING, f"show:{rule.id}:{event.show_id}:{event.event}"
        else:
            at, group = now, None
        if rule.push:
            for device in _push_targets(session):
                session.add(NotificationDelivery(
                    event_id=event.id, rule_id=rule.id, subscription_id=device.id,
                    group_key=group, status="PENDING", attempts=0, next_attempt_at=at,
                ))
        for destination_id in rule.destination_ids or []:
            destination = session.get(NotificationDestination, destination_id)
            if destination is None or not destination.enabled:
                continue
            kind = Kind(destination.kind)
            if kind in ACTION_KINDS:
                if not definition.actions or rule.delivery == "daily":
                    continue
                destination_at, destination_group = now, None
                if kind in MEDIA_SERVERS:
                    destination_at, destination_group = now + REFRESH_GROUPING, f"refresh:{destination.id}"
            else:
                destination_at, destination_group = at, group
            session.add(NotificationDelivery(
                event_id=event.id, rule_id=rule.id, destination_id=destination.id, group_key=destination_group,
                status="PENDING", attempts=0, next_attempt_at=destination_at,
            ))
    session.flush()


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    url: str | None
    tone: str
    tag: str | None


def compose(events: list[EventRow], *, daily: bool) -> Message:
    """One message for one event, several new downloads of a show, or a day's summary."""
    events = sorted(events, key=lambda event: event.occurred_at)
    first = events[0]
    tone = tone_of(first.event)
    if len(events) == 1 and not daily:
        return Message(first.title, first.body, first.url, tone, f"event-{first.id}")
    titles = [event.title for event in events[:_TITLES_IN_A_MESSAGE]]
    more = len(events) - len(titles)
    lines = [f"• {title}" for title in titles] + ([f"…and {more} more"] if more > 0 else [])
    if daily:
        counts: dict[str, int] = defaultdict(int)
        for event in events:
            counts[DEFINITIONS[Event(event.event)].when] += 1
        summary = "; ".join(f"{count}× {when}" for when, count in counts.items())
        return Message("WireLoft daily summary", f"{summary}\n" + "\n".join(lines), "/", "info", None)
    show = (first.data or {}).get("show")
    noun = {
        Event.EPISODE_DOWNLOADED: "new downloads", Event.EPISODE_REPLACED: "downloads replaced by a better version",
        Event.NEW_EPISODES: "new episodes found",
    }.get(Event(first.event), "events")
    title = f"{len(events)} {noun}" + (f" in {show}" if show else "")
    return Message(title, "\n".join(lines), first.url, tone, f"group-{first.id}")


@dataclass
class _Batch:
    delivery_ids: list[int]
    events: list[EventRow]
    destination: NotificationDestination | None
    subscription: PushSubscription | None
    daily: bool
    webhook_attempts: int


def _batches(session: Session, now: datetime) -> list[_Batch]:
    due = list(session.scalars(
        select(NotificationDelivery)
        .where(NotificationDelivery.status == "PENDING", NotificationDelivery.next_attempt_at <= now)
        .order_by(NotificationDelivery.id)
        .limit(_DUE_PER_PASS)
    ))
    grouped: dict[tuple, list[NotificationDelivery]] = {}
    for delivery in due:
        key = (delivery.group_key or f"single:{delivery.id}", delivery.destination_id, delivery.subscription_id)
        grouped.setdefault(key, []).append(delivery)
    batches = []
    for (group, destination_id, subscription_id), deliveries in grouped.items():
        if not group.startswith("single:"):
            # Everything still waiting in the group goes along, so a group is sent once.
            seen = {delivery.id for delivery in deliveries}
            deliveries += [
                delivery for delivery in session.scalars(select(NotificationDelivery).where(
                    NotificationDelivery.status == "PENDING", NotificationDelivery.group_key == group,
                    NotificationDelivery.destination_id.is_(None) if destination_id is None
                    else NotificationDelivery.destination_id == destination_id,
                    NotificationDelivery.subscription_id.is_(None) if subscription_id is None
                    else NotificationDelivery.subscription_id == subscription_id,
                )) if delivery.id not in seen
            ]
        destination = session.get(NotificationDestination, destination_id) if destination_id else None
        subscription = session.get(PushSubscription, subscription_id) if subscription_id else None
        batches.append(_Batch(
            [delivery.id for delivery in deliveries], [delivery.event for delivery in deliveries], destination, subscription,
            group.startswith("daily:"), max(delivery.attempts for delivery in deliveries),
        ))
    return batches


def _send(session: Session, batch: _Batch) -> Outcome | str:
    """Send one batch. Push answers SENT, EXPIRED or an Outcome; everything else an Outcome."""
    message = compose(batch.events, daily=batch.daily)
    if batch.subscription is not None:
        key = vapid_key(session)
        session.commit()
        return send_push(key, batch.subscription, {
            "title": message.title, "body": message.body, "url": message.url or "/", "tag": message.tag,
        })
    destination = batch.destination
    if destination is None:
        return Outcome(False, "The destination was deleted")
    config = config_of(destination)
    if config is None:
        return Outcome(False, "WireLoft cannot read this destination's settings. Enter them again")
    kind = Kind(destination.kind)
    session.commit()
    if kind == Kind.APPRISE:
        from .events import Tone

        return send_message(config, title=message.title, body=message.body, tone=Tone(message.tone))
    if kind in MEDIA_SERVERS:
        folders = sorted({str((event.data or {}).get("folder")) for event in batch.events if (event.data or {}).get("folder")})
        return refresh_media_server(kind, config, folders)
    if kind == Kind.WEBHOOK:
        return call_webhook(config, webhook_payload(batch.events[0]))
    return run_script(config, batch.events[0])


def _record(session: Session, batch: _Batch, outcome: Outcome | str, now: datetime) -> None:
    deliveries = [session.get(NotificationDelivery, delivery_id) for delivery_id in batch.delivery_ids]
    deliveries = [delivery for delivery in deliveries if delivery is not None and delivery.status == "PENDING"]
    if isinstance(outcome, str):
        if outcome == "EXPIRED" and batch.subscription is not None:
            device = session.get(PushSubscription, batch.subscription.id)
            if device is not None:
                session.delete(device)
            return
        outcome = Outcome(outcome == "SENT", None if outcome == "SENT" else "The device is no longer subscribed")
    destination = session.get(NotificationDestination, batch.destination.id) if batch.destination else None
    if destination is not None:
        record_attempt(destination, delivered=outcome.delivered, error=outcome.error)
    webhook = destination is not None and destination.kind == Kind.WEBHOOK
    for delivery in deliveries:
        delivery.attempts += 1
        if outcome.delivered:
            delivery.status, delivery.error, delivery.sent_at = "SENT", None, now
            continue
        delivery.error = outcome.error
        retries = WEBHOOK_RETRY_SECONDS if webhook else None
        if not outcome.retry:
            delivery.status = "FAILED"
        elif retries is not None and delivery.attempts <= len(retries):
            delivery.next_attempt_at = now + timedelta(seconds=retries[delivery.attempts - 1])
        elif retries is None and delivery.attempts < MAX_ATTEMPTS:
            delivery.next_attempt_at = now + timedelta(seconds=min(600, 15 * 2 ** (delivery.attempts - 1)))
        else:
            delivery.status = "FAILED"
    if (
        destination is not None and Kind(destination.kind) in ACTION_KINDS and not outcome.delivered
        and any(delivery.status == "FAILED" for delivery in deliveries)
    ):
        # A failing action is a problem, so the default "a task keeps failing" rule tells administrators.
        emit(
            session, Event.TASK_FAILING, title=f"{destination.name} failed",
            body=outcome.error or "The action failed", url="/settings?tab=notifications",
            dedupe_key=f"action:{destination.id}",
        )


def deliver_pending(session: Session, *, now: datetime | None = None) -> int:
    """Send everything that is due. Returns how many batches went out."""
    now = now or _now()
    batches = _batches(session, now)
    session.commit()
    sent = 0
    for batch in batches:
        if batch.destination is not None and not batch.destination.enabled:
            for delivery_id in batch.delivery_ids:
                delivery = session.get(NotificationDelivery, delivery_id)
                if delivery is not None:
                    delivery.status = "CANCELED"
            session.commit()
            continue
        try:
            outcome = _send(session, batch)
        except Exception as error:  # A destination must never stop the rest from being sent.
            logger.exception("Sending a notification failed")
            # An exception is a fault in WireLoft or a library, not a busy service: retrying gives the same result.
            outcome = Outcome(False, f"Sending failed ({type(error).__name__})", retry=False)
        _record(session, batch, outcome, _now())
        session.commit()
        sent += 1
    return sent
