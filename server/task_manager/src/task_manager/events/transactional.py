"""Queue domain events until the surrounding SQLAlchemy transaction commits."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from task_manager.events.emitters import emit_event


logger = logging.getLogger(__name__)
_PENDING_EVENTS_KEY = "wireloft.pending_events"
_COMMITTED_EVENT_BATCH_ADAPTERS: dict[str, "CommittedEventBatchAdapter"] = {}


@dataclass(frozen=True)
class PendingEvent:
    name: str
    data: dict[str, Any]


CommittedEventBatchAdapter = Callable[
    [tuple[PendingEvent, ...]],
    Iterable[PendingEvent],
]


def committed_event_batch_adapter(
        name: str,
) -> Callable[[CommittedEventBatchAdapter], CommittedEventBatchAdapter]:
    """Register a pure adapter that derives events from one committed event batch.

    Adapters receive the complete set of domain events queued by one outer
    transaction. They may return additional events, typically worker-specific
    request events. Adapters must use only the supplied event payloads: the
    transaction is already committed and no database work belongs in this hook.

    Registration is keyed so importing/reloading the same adapter is idempotent.
    Derived events are appended after the original domain events and are not fed
    through adapters again.
    """
    if not name:
        raise ValueError("Committed event batch adapters require a name")

    def decorator(adapter: CommittedEventBatchAdapter) -> CommittedEventBatchAdapter:
        _COMMITTED_EVENT_BATCH_ADAPTERS[name] = adapter
        return adapter

    return decorator


def unregister_committed_event_batch_adapter(name: str) -> None:
    """Remove a registered batch adapter, primarily for isolated tests."""
    _COMMITTED_EVENT_BATCH_ADAPTERS.pop(name, None)


def _derive_committed_events(
        pending: tuple[PendingEvent, ...],
) -> list[PendingEvent]:
    derived: list[PendingEvent] = []
    if not pending:
        return derived

    for name, adapter in tuple(_COMMITTED_EVENT_BATCH_ADAPTERS.items()):
        try:
            for item in adapter(pending):
                if not isinstance(item, PendingEvent):
                    raise TypeError(
                        f"Committed event batch adapter {name!r} returned "
                        f"{type(item).__name__}, expected PendingEvent"
                    )
                derived.append(item)
        except Exception:
            # The database commit has already succeeded. One downstream adapter
            # must not prevent domain events or other adapters from being emitted.
            logger.exception("Committed event batch adapter %s failed", name)

    return derived


def queue_event(session: Session, event_name: str, data: dict[str, Any] | None = None) -> None:
    """Publish an event only if the session's outer transaction commits."""
    pending = session.info.setdefault(_PENDING_EVENTS_KEY, [])
    pending.append(PendingEvent(event_name, dict(data or {})))


@event.listens_for(Session, "after_commit")
def _publish_committed_events(session: Session) -> None:
    # A nested SAVEPOINT committed, but the outer transaction is still pending.
    if session.in_nested_transaction():
        return

    pending: list[PendingEvent] = session.info.pop(_PENDING_EVENTS_KEY, [])
    committed = tuple(pending)
    emitted = [*committed, *_derive_committed_events(committed)]
    for item in emitted:
        try:
            emit_event(item.name, item.data)
        except Exception:
            # The database commit has already succeeded. Event transport failure must
            # be observable, but must not make the caller believe the commit rolled back.
            logger.exception("Failed to emit committed event %s", item.name)


@event.listens_for(Session, "after_rollback")
def _discard_rolled_back_events(session: Session) -> None:
    session.info.pop(_PENDING_EVENTS_KEY, None)


@event.listens_for(Session, "after_soft_rollback")
def _discard_soft_rolled_back_events(session: Session, previous_transaction) -> None:
    session.info.pop(_PENDING_EVENTS_KEY, None)
