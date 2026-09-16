from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def _task_item(
    task_id: int,
    *,
    finished_at: datetime | None = None,
    is_redownload: bool = False,
    status: str = "SUCCEEDED",
    message: str = "Download complete",
    last_error: str | None = None,
) -> dict:
    finished_at = finished_at or datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    return {
        "id": task_id,
        "definition_key": "download_movie",
        "resource_type": "media_download",
        "resource_id": 42,
        "status": status,
        "message": message,
        "last_error": last_error,
        "inputs": {"is_redownload": is_redownload},
        "result": {"data": {"is_redownload": is_redownload}},
        "started_at": finished_at,
        "finished_at": finished_at,
        "runtime_ms": 1000,
    }


class _FakeSession:
    def __init__(self, download, events=()):
        self.download = download
        self.events = list(events)

    def get(self, _model, media_download_id: int):
        return self.download if media_download_id == self.download.id else None

    def scalar(self, _statement):
        return len(self.events)

    def scalars(self, _statement):
        return iter(self.events)


def test_download_history_projects_corrupted_artifact_after_task_run(monkeypatch):
    from backend.api.endpoints.media_downloads import history
    from backend.api.models.media_download_history import MediaDownloadHistoryPageRead

    observed_at = datetime(2026, 9, 14, 12, 5, tzinfo=timezone.utc)
    artifact_error = "File at '/downloads/movie.mp4' is only 10 bytes, well under the 1000 recorded when it finished downloading"
    download = SimpleNamespace(
        id=42,
        type="movie",
        artifact_status="corrupted",
        artifact_error=artifact_error,
        file_path="/downloads/movie.mp4",
        updated_at=observed_at,
    )

    calls = []

    def fake_query_ledger(_session, **kwargs):
        calls.append(kwargs)
        return {
            "items": [_task_item(7)],
            "total": 1,
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "has_more": False,
        }

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download), 42)
    parsed = MediaDownloadHistoryPageRead.model_validate(result)

    assert parsed.total == 2
    assert parsed.items[0].key == "artifact-current"
    assert parsed.items[0].status == "corrupted"
    assert parsed.items[0].activity == "File watcher"
    assert parsed.items[0].error == artifact_error
    assert parsed.items[0].occurred_at == observed_at
    assert parsed.items[1].key == "task-7"
    assert parsed.items[1].status == "downloaded"
    assert parsed.items[1].activity == "Initial download"
    assert calls == [{
        "definition_key": "download_movie",
        "resource_type": "media_download",
        "resource_ids": [42],
        "order_by": "started_at",
        "order": "desc",
        "offset": 0,
        "limit": 50,
    }]


def test_download_history_merges_deletion_event_chronologically(monkeypatch):
    from backend.api.endpoints.media_downloads import history
    from backend.api.models.media_download_history import MediaDownloadHistoryPageRead

    download = SimpleNamespace(
        id=42,
        type="episode",
        artifact_status="available",
        artifact_error=None,
        file_path="/downloads/episode.mp4",
        updated_at=datetime(2026, 9, 16, 12, 10, tzinfo=timezone.utc),
    )
    event = SimpleNamespace(
        id=9,
        media_download_id=42,
        event_type="deleted",
        file_path="/downloads/episode.mp4",
        occurred_at=datetime(2026, 9, 16, 12, 5, tzinfo=timezone.utc),
    )

    def fake_query_ledger(_session, **kwargs):
        return {
            "items": [
                _task_item(
                    11,
                    finished_at=datetime(2026, 9, 16, 12, 9, tzinfo=timezone.utc),
                    is_redownload=True,
                ),
                _task_item(7, finished_at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)),
            ],
            "total": 2,
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "has_more": False,
        }

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download, [event]), 42)
    parsed = MediaDownloadHistoryPageRead.model_validate(result)

    assert parsed.total == 3
    assert [item.status for item in parsed.items] == ["redownloaded", "deleted", "downloaded"]
    assert [item.activity for item in parsed.items] == ["Redownload", "WireLoft", "Initial download"]
    assert parsed.items[1].key == "event-9"
    assert parsed.items[1].occurred_at == event.occurred_at


def test_download_history_normalizes_task_failures(monkeypatch):
    from backend.api.endpoints.media_downloads import history

    download = SimpleNamespace(
        id=42,
        type="episode",
        artifact_status="absent",
        artifact_error=None,
        file_path="/downloads/episode.mp4",
        updated_at=datetime(2026, 9, 14, 12, 5, tzinfo=timezone.utc),
    )

    def fake_query_ledger(_session, **kwargs):
        return {
            "items": [_task_item(
                8,
                status="FAILED",
                message="Download failed",
                last_error="HTTP 500",
            )],
            "total": 1,
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "has_more": False,
        }

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download), 42)

    assert result["items"] == [{
        "key": "task-8",
        "status": "error",
        "activity": "Initial download",
        "occurred_at": datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        "error": "HTTP 500",
    }]


def test_download_history_paginates_combined_history(monkeypatch):
    from backend.api.endpoints.media_downloads import history

    download = SimpleNamespace(
        id=42,
        type="movie_extra",
        artifact_status="missing",
        artifact_error="File not found at '/downloads/extra.mp4'",
        file_path="/downloads/extra.mp4",
        updated_at=datetime(2026, 9, 14, 12, 5, tzinfo=timezone.utc),
    )

    requested = []

    def fake_query_ledger(_session, **kwargs):
        requested.append((kwargs["offset"], kwargs["limit"]))
        return {
            "items": [_task_item(3), _task_item(2), _task_item(1)],
            "total": 3,
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "has_more": False,
        }

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download), 42, offset=2, limit=2)

    assert requested == [(0, 4)]
    assert len(result["items"]) == 2
    assert result["total"] == 4
    assert result["has_more"] is False


def test_download_history_does_not_add_healthy_artifact(monkeypatch):
    from backend.api.endpoints.media_downloads import history

    download = SimpleNamespace(
        id=42,
        type="episode",
        artifact_status="available",
        artifact_error=None,
        file_path="/downloads/episode.mp4",
        updated_at=datetime(2026, 9, 14, 12, 5, tzinfo=timezone.utc),
    )

    definition_keys = []

    def fake_query_ledger(_session, **kwargs):
        definition_keys.append(kwargs["definition_key"])
        task = _task_item(3)
        task["definition_key"] = kwargs["definition_key"]
        return {
            "items": [task],
            "total": 1,
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "has_more": False,
        }

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download), 42)

    assert definition_keys == ["download_episode"]
    assert result["total"] == 1
    assert result["items"][0] == {
        "key": "task-3",
        "status": "downloaded",
        "activity": "Initial download",
        "occurred_at": datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        "error": None,
    }
