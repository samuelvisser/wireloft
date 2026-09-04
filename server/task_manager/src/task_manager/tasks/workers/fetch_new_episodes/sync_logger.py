from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.db.models import Show


SYNC_LOG_META_KEY = "episode_sync_log"
SYNC_LOG_LIMIT = 10


def append_sync_log(
    show: Show,
    *,
    episodes_found: int,
    status: str,
    will_retry: bool | None = None,
    synced_at: datetime | None = None,
) -> None:
    """Append one bounded sync-history entry to a show."""
    raw = show.get_meta(SYNC_LOG_META_KEY)
    try:
        history = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        history = []
    if not isinstance(history, list):
        history = []

    entry = {
        "synced_at": (synced_at or datetime.now(timezone.utc)).isoformat(),
        "episodes_found": max(0, int(episodes_found)),
        "status": status,
    }
    if will_retry is not None:
        entry["will_retry"] = will_retry

    history.insert(0, entry)
    show.set_meta(SYNC_LOG_META_KEY, json.dumps(history[:SYNC_LOG_LIMIT]))


def task_will_retry(progress) -> bool:
    """Return whether the TaskRun backing a progress sink still has a retry left."""
    run = getattr(progress, "run", None)
    if run is None:
        return False
    attempt_count = int(getattr(run, "attempt_count", 0) or 0)
    max_retries = int(getattr(run, "max_retries", 0) or 0)
    return attempt_count <= max_retries
