"""Event emission utilities for triggering tasks based on data changes."""
from __future__ import annotations

from typing import Optional, Any
from task_manager.events.registry import get_wireloft_event_emitter


def emit_event(event_name: str, data: Optional[dict[str, Any]] = None) -> None:
    """
    Submit a domain event to the WireLoft event executor.

    Args:
        event_name: Name of the event (e.g., "show.added", "episode.published_final")
        data: Optional event data including resource_id and other metadata
    """
    emitter = get_wireloft_event_emitter()

    emitter.emit(event_name, **(data or {}))
