"""Queue domain events until the surrounding SQLAlchemy transaction commits."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from task_manager.events.emitters import emit_event


logger = logging.getLogger(__name__)
_PENDING_EVENTS_KEY = "wireloft.pending_events"


@dataclass(frozen=True)
class PendingEvent:
    name: str
    data: dict[str, Any]


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
    for item in pending:
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
