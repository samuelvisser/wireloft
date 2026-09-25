from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Iterable
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


def _history_operation_ids(metadata: Mapping[str, Any] | None) -> set[str]:
    values = metadata or {}
    operation_ids: set[str] = set()
    operation_id = values.get("operation_id")
    if isinstance(operation_id, str) and operation_id:
        operation_ids.add(operation_id)
    multiple = values.get("operation_ids")
    if isinstance(multiple, (list, tuple, set)):
        operation_ids.update(
            str(value) for value in multiple
            if isinstance(value, str) and value
        )
    return operation_ids


def _history_task_run_id(metadata: Mapping[str, Any] | None) -> int | None:
    value = (metadata or {}).get("task_run_id")
    return value if isinstance(value, int) else None


def record_media_download_operation_history_once(
    session: Session,
    media_download_id: int,
    action: MediaDownloadHistoryAction | str,
    *,
    operation_ids: Iterable[str],
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> MediaDownloadHistory | None:
    """Record one operation-correlated action, suppressing concurrent duplicates."""
    if session.scalar(
        select(MediaDownloadBase.id).where(MediaDownloadBase.id == media_download_id)
    ) is None:
        return None

    correlated_ids = {
        str(operation_id) for operation_id in operation_ids if operation_id
    }
    action_value = action.value if isinstance(action, MediaDownloadHistoryAction) else str(action)
    task_run_id = _history_task_run_id(metadata)
    if task_run_id is not None:
        recent = session.scalars(
            select(MediaDownloadHistory)
            .where(
                MediaDownloadHistory.media_download_id == media_download_id,
                MediaDownloadHistory.action == action_value,
            )
            .order_by(MediaDownloadHistory.id.desc())
            .limit(25)
        )
        for entry in recent:
            if _history_task_run_id(entry.event_metadata) == task_run_id:
                return entry

    merged_metadata = dict(metadata or {})
    if correlated_ids and not _history_operation_ids(merged_metadata):
        if len(correlated_ids) == 1:
            merged_metadata["operation_id"] = next(iter(correlated_ids))
        else:
            merged_metadata["operation_ids"] = sorted(correlated_ids)

    return record_media_download_history(
        session,
        media_download_id,
        action_value,
        metadata=merged_metadata,
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
