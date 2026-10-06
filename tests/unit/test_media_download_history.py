from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


def _entry(action: str, metadata: dict):
    return SimpleNamespace(
        id=7,
        media_download_id=42,
        action=action,
        event_metadata=metadata,
        occurred_at=datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc),
    )


def test_created_download_history_is_not_presented_as_queued():
    from backend.api.endpoints.media_downloads.history import _MediaDownloadHistoryViewSource
    from backend.api.models.media_download_history import MediaDownloadHistoryEntryRead

    entry = MediaDownloadHistoryEntryRead.model_validate(
        _MediaDownloadHistoryViewSource(_entry("created", {}))
    )

    assert entry.label == "Download created"
    assert entry.status == "not_downloaded"


def test_completed_download_history_is_formatted_by_backend():
    from backend.api.endpoints.media_downloads.history import _MediaDownloadHistoryViewSource
    from backend.api.models.media_download_history import MediaDownloadHistoryEntryRead

    entry = MediaDownloadHistoryEntryRead.model_validate(_MediaDownloadHistoryViewSource(_entry("completed", {
        "duration_ms": 62_345,
        "is_redownload": True,
        "downloaded_bytes": 10 * 1024 * 1024,
        "format_downloaded": "mp4",
    })))

    assert entry.label == "Redownload completed"
    assert entry.status == "redownloaded"
    assert entry.duration_ms == 62_345
    assert entry.duration == "1m 02s"
    assert entry.detail == "10.0 MB · mp4"
    assert entry.metadata["is_redownload"] is True


def test_failed_download_history_keeps_error_and_attempt_duration():
    from backend.api.endpoints.media_downloads.history import _MediaDownloadHistoryViewSource
    from backend.api.models.media_download_history import MediaDownloadHistoryEntryRead

    entry = MediaDownloadHistoryEntryRead.model_validate(_MediaDownloadHistoryViewSource(_entry("failed", {
        "duration_ms": 12_500,
        "is_redownload": False,
        "error": "connection reset",
        "error_type": "DownloadError",
    })))

    assert entry.label == "Download failed"
    assert entry.status == "error"
    assert entry.duration == "12.5 s"
    assert entry.detail == "connection reset"
    assert entry.metadata["error_type"] == "DownloadError"


def test_interrupted_download_history_shows_premature_shutdown():
    from backend.api.endpoints.media_downloads.history import _MediaDownloadHistoryViewSource
    from backend.api.models.media_download_history import MediaDownloadHistoryEntryRead

    entry = MediaDownloadHistoryEntryRead.model_validate(
        _MediaDownloadHistoryViewSource(_entry("interrupted", {
            "duration_ms": 42_000,
            "is_redownload": False,
            "reason": "Canceled due to premature shutdown",
        }))
    )

    assert entry.label == "Canceled due to premature shutdown"
    assert entry.status == "cancelled"
    assert entry.duration == "42.0 s"
    assert entry.detail is None


def test_download_attempt_metadata_uses_elapsed_wall_time():
    from backend.services.media_download_history import download_attempt_metadata

    started = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)
    finished = started + timedelta(seconds=3, milliseconds=250)
    metadata = download_attempt_metadata(
        started_at=started,
        finished_at=finished,
        is_redownload=False,
        error=RuntimeError("boom"),
    )

    assert metadata["duration_ms"] == 3250
    assert metadata["is_redownload"] is False
    assert metadata["error"] == "boom"
    assert metadata["error_type"] == "RuntimeError"
