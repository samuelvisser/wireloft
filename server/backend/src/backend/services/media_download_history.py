from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.media_download import MediaDownloadBase, MediaDownloadHistory
from backend.types.media_download_history_types import MediaDownloadHistoryAction


def record_media_download_history(
    session: Session,
    media_download_id: int,
    action: MediaDownloadHistoryAction | str,
    *,
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> MediaDownloadHistory:
    """Append one durable history event inside the caller's transaction."""
    action_value = action.value if isinstance(action, MediaDownloadHistoryAction) else str(action)
    entry = MediaDownloadHistory(
        media_download_id=media_download_id,
        action=action_value,
        event_metadata=dict(metadata or {}),
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    session.add(entry)
    return entry


def record_media_download_history_if_exists(
    session: Session,
    media_download_id: int,
    action: MediaDownloadHistoryAction | str,
    *,
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> MediaDownloadHistory | None:
    """Append a history event only while the owning MediaDownload still exists."""
    existing_id = session.scalar(
        select(MediaDownloadBase.id).where(MediaDownloadBase.id == media_download_id)
    )
    if existing_id is None:
        return None
    return record_media_download_history(
        session,
        media_download_id,
        action,
        metadata=metadata,
        occurred_at=occurred_at,
    )


def download_attempt_metadata(
    *,
    started_at: datetime,
    finished_at: datetime,
    is_redownload: bool,
    error: BaseException | str | None = None,
    **values: Any,
) -> dict[str, Any]:
    """Build JSON-safe metadata shared by terminal download history events."""
    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    metadata: dict[str, Any] = {
        "duration_ms": duration_ms,
        "is_redownload": bool(is_redownload),
    }

    if error is not None:
        metadata["error"] = str(error)
        if isinstance(error, BaseException):
            metadata["error_type"] = type(error).__name__

    for key, value in values.items():
        if value is not None:
            metadata[key] = value
    return metadata
