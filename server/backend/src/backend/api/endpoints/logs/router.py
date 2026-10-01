from __future__ import annotations

from fastapi import APIRouter, Query

from backend.api.models.logs import ApplicationLogEntryRead, ApplicationLogPageRead
from backend.logging_buffer import get_application_logs, max_application_log_entries


router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("", response_model=ApplicationLogPageRead)
def application_logs(
    level: str | None = None,
    search: str | None = None,
    limit: int = Query(default=20_000, ge=1, le=20_000),
):
    """Return retained application-wide log records in chronological order."""

    entries = get_application_logs()
    if level:
        requested_level = level.upper()
        entries = [entry for entry in entries if entry.level == requested_level]
    if search:
        needle = search.casefold()
        entries = [
            entry
            for entry in entries
            if needle in entry.logger.casefold()
            or needle in entry.message.casefold()
            or (entry.exception is not None and needle in entry.exception.casefold())
        ]

    total = len(entries)
    if len(entries) > limit:
        entries = entries[-limit:]

    return ApplicationLogPageRead(
        items=[ApplicationLogEntryRead.model_validate(entry) for entry in entries],
        total=total,
        retained_limit=max_application_log_entries(),
    )
