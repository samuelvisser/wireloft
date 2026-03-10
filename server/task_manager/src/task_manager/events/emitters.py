"""Event emission utilities for triggering tasks based on data changes."""
from __future__ import annotations

import asyncio
from typing import Optional, Any
from task_manager.events.registry import get_wireloft_event_emitter


def emit_event(event_name: str, data: Optional[dict[str, Any]] = None) -> None:
    """
    Emit an event to trigger registered tasks in a fire-and-forget manner.

    This function creates a background task for event emission, ensuring that
    the caller is not blocked waiting for event handlers to execute.

    Args:
        event_name: Name of the event (e.g., "show.added", "episode.published_final")
        data: Optional event data including resource_id and other metadata
    """
    emitter = get_wireloft_event_emitter()

    async def _emit():
        await emitter.emit(event_name, data or {})

    # Fire-and-forget: create background task without awaiting
    try:
        asyncio.create_task(_emit())
    except RuntimeError:
        # No event loop running, emit synchronously
        # This fallback handles edge cases like testing
        asyncio.run(_emit())
