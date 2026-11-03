"""What messages and actions can be about, and recording that something happened.

``emit`` stores the event and the deliveries every matching rule asks for, in the caller's transaction, so the
event is only sent once whatever caused it is committed. Sending happens later, in the background.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import NotificationEvent as EventRow


class Event(StrEnum):
    EPISODE_DOWNLOADED = "episode_downloaded"
    EPISODE_REPLACED = "episode_replaced"
    EPISODE_DELETED = "episode_deleted"
    DOWNLOAD_FAILED = "download_failed"
    NEW_EPISODES = "new_episodes"
    SIGN_IN_NEEDED = "sign_in_needed"
    TASK_FAILING = "task_failing"
    DISK_ALMOST_FULL = "disk_almost_full"
    UPDATE_AVAILABLE = "update_available"
    EVERYTHING = "everything"
    """Only for a daily summary: everything that happened that day."""


class Tone(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"


@dataclass(frozen=True)
class EventDefinition:
    event: Event
    when: str
    """How a rule's sentence starts: "When <when> …"."""
    tone: Tone
    shows: bool
    """Whether the event belongs to a show, so a rule can choose which shows."""
    actions: bool
    """Whether actions (media server refresh, webhook, script) can run on it."""
    problem: bool = False


EVENTS: tuple[EventDefinition, ...] = (
    EventDefinition(Event.EPISODE_DOWNLOADED, "an episode is downloaded", Tone.SUCCESS, True, True),
    EventDefinition(Event.EPISODE_REPLACED, "a download is replaced by a better version", Tone.SUCCESS, True, True),
    EventDefinition(Event.EPISODE_DELETED, "a download is deleted", Tone.INFO, True, True),
    EventDefinition(Event.DOWNLOAD_FAILED, "a download fails after its retries", Tone.FAILURE, True, False, True),
    EventDefinition(Event.NEW_EPISODES, "new episodes are found but not downloaded", Tone.INFO, True, False),
    EventDefinition(Event.SIGN_IN_NEEDED, "the Daily Wire sign-in expires", Tone.FAILURE, False, False, True),
    EventDefinition(Event.TASK_FAILING, "a task keeps failing", Tone.FAILURE, False, False, True),
    EventDefinition(Event.DISK_ALMOST_FULL, "the disk is almost full", Tone.FAILURE, False, False, True),
    EventDefinition(Event.UPDATE_AVAILABLE, "a WireLoft update is out", Tone.INFO, False, False),
    EventDefinition(Event.EVERYTHING, "anything happens", Tone.INFO, True, False),
)
DEFINITIONS = {definition.event: definition for definition in EVENTS}


def emit(
    session: Session,
    event: Event,
    *,
    title: str,
    body: str = "",
    show_id: int | None = None,
    url: str | None = None,
    data: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    occurred_at: datetime | None = None,
) -> EventRow:
    """Record that something happened, and queue it for every rule that wants it."""
    from .delivery import enqueue

    row = EventRow(
        event=event.value, occurred_at=occurred_at or datetime.now(timezone.utc), show_id=show_id,
        title=title[:255], body=body, url=url, data=data or {}, dedupe_key=dedupe_key,
    )
    session.add(row)
    session.flush()
    enqueue(session, row)
    return row
