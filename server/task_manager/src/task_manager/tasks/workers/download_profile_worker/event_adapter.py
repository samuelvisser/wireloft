"""Translate committed domain events into scoped Download Profile worker requests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.types.episode_types import EpisodePublishStatus
from task_manager.events.transactional import (
    PendingEvent,
    committed_event_batch_adapter,
)


DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT = "download_profile.run_requested"

DownloadProfileRunResourceType = Literal["download_profile", "show", "episode"]
_PUBLISHED_DOWNLOAD_STATUSES = frozenset({
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value,
    EpisodePublishStatus.PUBLISHED_FINAL.value,
})
_PROFILE_EVENTS = frozenset({
    "download_profile.added",
    "download_profile.updated",
})
_EPISODE_EVENTS = frozenset({
    "episode.published_with_countdown",
    "episode.published_final",
})


@dataclass(frozen=True)
class _RunRequest:
    resource_type: DownloadProfileRunResourceType
    resource_id: int
    show_id: int | None = None

    def as_event(self) -> PendingEvent:
        return PendingEvent(
            DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT,
            {
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
            },
        )


def _int_value(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resource_id(event: PendingEvent) -> int | None:
    return _int_value(event.data.get("resource_id", event.data.get("id")))


def _status_value(value) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _request_for_event(event: PendingEvent) -> _RunRequest | None:
    resource_id = _resource_id(event)
    if resource_id is None or resource_id <= 0:
        return None

    if event.name == "show.indexed":
        return _RunRequest("show", resource_id, show_id=resource_id)

    if event.name in _PROFILE_EVENTS:
        return _RunRequest(
            "download_profile",
            resource_id,
            show_id=_int_value(event.data.get("show_id")),
        )

    if event.name in {"episode.added", "episode.status_updated"}:
        if _status_value(event.data.get("status")) not in _PUBLISHED_DOWNLOAD_STATUSES:
            return None
    elif event.name not in _EPISODE_EVENTS:
        return None

    return _RunRequest(
        "episode",
        resource_id,
        show_id=_int_value(event.data.get("show_id")),
    )


@committed_event_batch_adapter("download_profile_worker")
def adapt_download_profile_events(
        events: tuple[PendingEvent, ...],
) -> tuple[PendingEvent, ...]:
    """Reduce committed domain events to the Download Profile runs they require.

    Domain code only reports facts about shows, episodes, and profiles. This
    adapter owns the policy that translates those facts into worker requests.

    A show-scoped request subsumes profile- and episode-scoped requests for that
    same show within the same committed transaction. Exact duplicate scopes are
    also collapsed. No time-window or cross-transaction deduplication is used.
    """
    requests: list[_RunRequest] = []
    seen: set[tuple[str, int]] = set()

    for event in events:
        request = _request_for_event(event)
        if request is None:
            continue

        key = (request.resource_type, request.resource_id)
        if key in seen:
            continue
        seen.add(key)
        requests.append(request)

    show_ids = {
        request.resource_id
        for request in requests
        if request.resource_type == "show"
    }

    return tuple(
        request.as_event()
        for request in requests
        if (
            request.resource_type == "show"
            or request.show_id is None
            or request.show_id not in show_ids
        )
    )
