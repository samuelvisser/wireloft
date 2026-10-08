"""The WireLoft events users can route to notification destinations.

Both Web Push devices and Apprise channels pick from the same events, so the
classification of a finished operation lives here, below the API layer, where
the workers and the endpoints can share it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from task_manager.scheduler.db import TaskOperation

TERMINAL_STATUSES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELED"})
MAX_ALERT_AGE = timedelta(hours=24)


class NotificationEvent(StrEnum):
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    NEW_EPISODES = "new_episodes"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    OPERATIONS = "operations"


class EventTone(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class NotificationEventDefinition:
    event: NotificationEvent
    label: str
    description: str
    tone: EventTone


EVENT_DEFINITIONS: tuple[NotificationEventDefinition, ...] = (
    NotificationEventDefinition(
        NotificationEvent.DOWNLOAD_COMPLETED, "Download completed",
        "A media download finished", EventTone.SUCCESS,
    ),
    NotificationEventDefinition(
        NotificationEvent.DOWNLOAD_FAILED, "Download failed",
        "A media download failed or only partly completed", EventTone.FAILURE,
    ),
    NotificationEventDefinition(
        NotificationEvent.NEW_EPISODES, "New episodes found",
        "A scan found new content in The Daily Wire", EventTone.INFO,
    ),
    NotificationEventDefinition(
        NotificationEvent.TASK_COMPLETED, "Task completed",
        "Scheduled or background work finished, such as a metadata refresh", EventTone.SUCCESS,
    ),
    NotificationEventDefinition(
        NotificationEvent.TASK_FAILED, "Task failed",
        "Scheduled, background or manual work failed", EventTone.FAILURE,
    ),
    NotificationEventDefinition(
        NotificationEvent.OPERATIONS, "Other operations",
        "Other manual actions and canceled work", EventTone.NEUTRAL,
    ),
)

# New destinations start with the events that need attention.
DEFAULT_EVENTS: frozenset[NotificationEvent] = frozenset({
    NotificationEvent.DOWNLOAD_FAILED,
    NotificationEvent.TASK_FAILED,
})


def _is_download(operation: TaskOperation) -> bool:
    return operation.kind.startswith("media.download") or operation.resource_type == "media_download"


def _episodes_found(operation: TaskOperation) -> int:
    data = (operation.result or {}).get("data")
    found = data.get("episodes_found") if isinstance(data, dict) else None
    return found if isinstance(found, int) else 0


def operation_event(operation: TaskOperation) -> NotificationEvent:
    if operation.status in ("FAILED", "PARTIAL"):
        return NotificationEvent.DOWNLOAD_FAILED if _is_download(operation) else NotificationEvent.TASK_FAILED
    if operation.status != "SUCCEEDED":
        return NotificationEvent.OPERATIONS
    if _is_download(operation):
        return NotificationEvent.DOWNLOAD_COMPLETED
    if _episodes_found(operation) > 0:
        return NotificationEvent.NEW_EPISODES
    if operation.source != "UI" or "cron" in operation.kind or "task" in operation.kind:
        return NotificationEvent.TASK_COMPLETED
    return NotificationEvent.OPERATIONS


def operation_url(event: NotificationEvent) -> str:
    if event in (NotificationEvent.DOWNLOAD_COMPLETED, NotificationEvent.DOWNLOAD_FAILED):
        return "/downloads"
    if event in (NotificationEvent.TASK_COMPLETED, NotificationEvent.TASK_FAILED):
        return "/tasks"
    return "/"


@dataclass(frozen=True)
class NotificationMessage:
    event: NotificationEvent
    title: str
    body: str
    operation_id: str
    url: str


def notification_message(operation: TaskOperation) -> NotificationMessage:
    event = operation_event(operation)
    labels = {
        "SUCCEEDED": "completed",
        "PARTIAL": "partially completed",
        "FAILED": "failed",
        "CANCELED": "canceled",
    }
    summary = (operation.result or {}).get("summary")
    body = summary if isinstance(summary, str) and summary.strip() else operation.message
    if not body:
        body = operation.error or operation.title
    return NotificationMessage(
        event=event,
        title=f"WireLoft: {operation.title} {labels.get(operation.status, 'finished')}",
        body=str(body)[:350],
        operation_id=operation.id,
        url=operation_url(event),
    )
