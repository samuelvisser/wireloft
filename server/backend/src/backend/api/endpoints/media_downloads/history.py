from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.models.media_download_history import (
    MediaDownloadHistoryEntryRead,
    MediaDownloadHistoryPageRead,
)
from backend.db.models.media_download import MediaDownloadBase, MediaDownloadHistory
from backend.types.media_download_history_types import MediaDownloadHistoryAction


def _format_duration(duration_ms: int | None) -> str | None:
    if duration_ms is None:
        return None
    if duration_ms < 1000:
        return f"{duration_ms} ms"

    total_seconds = duration_ms / 1000
    if total_seconds < 60:
        return f"{total_seconds:.1f} s"

    whole_seconds = int(total_seconds)
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


def _format_publish_status(value: object) -> str | None:
    labels = {
        "published_with_countdown": "Countdown version",
        "published_final": "Final version",
    }
    return labels.get(value) if isinstance(value, str) else None


def _format_bytes(value: object) -> str | None:
    if not isinstance(value, int) or value < 0:
        return None
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return None


def _presentation(entry: MediaDownloadHistory) -> tuple[str, str, str | None]:
    metadata = entry.event_metadata or {}
    action = entry.action

    if action == MediaDownloadHistoryAction.CREATED:
        # Creating the persistent MediaDownload row is not a queue event. Keep it
        # visually distinct from the subsequent media.download operation so one
        # newly-created download is not presented as having been queued twice.
        return "Download created", "not_downloaded", None
    if action == MediaDownloadHistoryAction.QUEUED:
        return (
            "Redownload queued" if metadata.get("is_redownload") else "Download queued",
            "pending",
            None,
        )
    if action == MediaDownloadHistoryAction.PRIORITIZED:
        return "Download prioritized", "pending", None
    if action == MediaDownloadHistoryAction.RETRY_REQUESTED:
        return "Retry requested", "pending", None
    if action == MediaDownloadHistoryAction.RESTARTED:
        return (
            "Redownload restarted" if metadata.get("is_redownload") else "Download restarted",
            "pending",
            None,
        )
    if action == MediaDownloadHistoryAction.STARTED:
        return (
            "Redownload started" if metadata.get("is_redownload") else "Download started",
            "downloading",
            _format_publish_status(metadata.get("started_publish_status")),
        )
    if action == MediaDownloadHistoryAction.COMPLETED:
        detail_parts = [
            value
            for value in (
                _format_publish_status(metadata.get("started_publish_status")),
                _format_bytes(metadata.get("downloaded_bytes")),
                str(metadata["format_downloaded"]) if metadata.get("format_downloaded") else None,
            )
            if value
        ]
        return (
            "Redownload completed" if metadata.get("is_redownload") else "Download completed",
            "redownloaded" if metadata.get("is_redownload") else "downloaded",
            " · ".join(detail_parts) or None,
        )
    if action == MediaDownloadHistoryAction.FAILED:
        return (
            "Redownload failed" if metadata.get("is_redownload") else "Download failed",
            "error",
            str(metadata.get("error")) if metadata.get("error") else None,
        )
    if action == MediaDownloadHistoryAction.CANCEL_REQUESTED:
        reason = metadata.get("reason")
        return "Cancellation requested", "cancelled", str(reason) if reason else None
    if action == MediaDownloadHistoryAction.CANCELLED:
        reason = metadata.get("reason")
        return "Download cancelled", "cancelled", str(reason) if reason else None
    if action == MediaDownloadHistoryAction.ARTIFACT_REMOVED:
        path = metadata.get("file_path")
        return "Previous file removed", "not_downloaded", str(path) if path else None
    if action == MediaDownloadHistoryAction.ARTIFACT_MISSING:
        error = metadata.get("error")
        return "File missing", "missing", str(error) if error else None
    if action == MediaDownloadHistoryAction.ARTIFACT_CORRUPTED:
        error = metadata.get("error")
        return "File corrupted", "corrupted", str(error) if error else None
    if action == MediaDownloadHistoryAction.ARTIFACT_RESTORED:
        return "File available again", "downloaded", None
    if action == MediaDownloadHistoryAction.ARTIFACT_RENAMED:
        old_path = metadata.get("old_path")
        new_path = metadata.get("new_path")
        detail = f"{old_path} → {new_path}" if old_path and new_path else None
        return "File renamed", "downloaded", detail

    return action.replace("_", " ").title(), "pending", None


@dataclass(frozen=True)
class _MediaDownloadHistoryViewSource:
    entry: MediaDownloadHistory

    @property
    def id(self) -> int:
        return self.entry.id

    @property
    def media_download_id(self) -> int:
        return self.entry.media_download_id

    @property
    def action(self) -> str:
        return self.entry.action

    @property
    def occurred_at(self):
        return self.entry.occurred_at

    @property
    def metadata(self) -> dict:
        return dict(self.entry.event_metadata or {})

    @property
    def duration_ms(self) -> int | None:
        value = self.metadata.get("duration_ms")
        return value if isinstance(value, int) else None

    @property
    def duration(self) -> str | None:
        return _format_duration(self.duration_ms)

    @property
    def label(self) -> str:
        return _presentation(self.entry)[0]

    @property
    def status(self) -> str:
        return _presentation(self.entry)[1]

    @property
    def detail(self) -> str | None:
        return _presentation(self.entry)[2]


def get_media_download_history(
    s: Session,
    media_download_id: int,
    *,
    offset: int = 0,
    limit: int = 50,
) -> MediaDownloadHistoryPageRead:
    """Return the append-only domain history for one MediaDownload."""
    if s.get(MediaDownloadBase, media_download_id) is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    total = s.scalar(
        select(func.count())
        .select_from(MediaDownloadHistory)
        .where(MediaDownloadHistory.media_download_id == media_download_id)
    ) or 0

    entries = list(
        s.scalars(
            select(MediaDownloadHistory)
            .where(MediaDownloadHistory.media_download_id == media_download_id)
            .order_by(
                MediaDownloadHistory.occurred_at.desc(),
                MediaDownloadHistory.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )

    items = [
        MediaDownloadHistoryEntryRead.model_validate(
            _MediaDownloadHistoryViewSource(entry)
        )
        for entry in entries
    ]
    return MediaDownloadHistoryPageRead(
        items=items,
        total=int(total),
        offset=offset,
        limit=limit,
        has_more=offset + len(items) < total,
    )
