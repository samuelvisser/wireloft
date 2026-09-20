from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def _task_item(task_id: int):
    from backend.api.models.tasks import TaskLedgerEntryRead

    finished_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    return TaskLedgerEntryRead.model_validate({
        "id": task_id,
        "definition_key": "download_movie",
        "resource_type": "media_download",
        "resource_id": 42,
        "status": "SUCCEEDED",
        "message": "Download complete",
        "last_error": None,
        "inputs": {"is_redownload": False},
        "result": {"data": {"is_redownload": False}},
        "started_at": finished_at,
        "finished_at": finished_at,
        "runtime_ms": 1000,
    })


class _FakeSession:
    def __init__(self, download):
        self.download = download

    def get(self, _model, media_download_id: int):
        return self.download if media_download_id == self.download.id else None


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
        from backend.api.models.tasks import TaskLedgerPageRead
        return TaskLedgerPageRead(
            items=[_task_item(7)],
            total=1,
            offset=kwargs["offset"],
            limit=kwargs["limit"],
            has_more=False,
        )

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download), 42)
    parsed = MediaDownloadHistoryPageRead.model_validate(result)

    assert parsed.total == 2
    assert parsed.items[0].source == "artifact"
    assert parsed.items[0].artifact_status == "corrupted"
    assert parsed.items[0].artifact_error == artifact_error
    assert parsed.items[0].file_path == "/downloads/movie.mp4"
    assert parsed.items[0].observed_at == observed_at
    assert parsed.items[1].source == "task"
    assert parsed.items[1].id == 7
    assert calls == [{
        "definition_key": "download_movie",
        "resource_type": "media_download",
        "resource_ids": [42],
        "order_by": "started_at",
        "order": "desc",
        "offset": 0,
        "limit": 50,
    }]


def test_download_history_paginates_past_artifact_entry(monkeypatch):
    from backend.api.endpoints.media_downloads import history

    download = SimpleNamespace(
        id=42,
        type="movie_extra",
        artifact_status="missing",
        artifact_error="File not found at '/downloads/extra.mp4'",
        file_path="/downloads/extra.mp4",
        updated_at=datetime(2026, 9, 14, 12, 5, tzinfo=timezone.utc),
    )

    requested_offsets = []

    def fake_query_ledger(_session, **kwargs):
        requested_offsets.append(kwargs["offset"])
        from backend.api.models.tasks import TaskLedgerPageRead
        return TaskLedgerPageRead(
            items=[_task_item(2), _task_item(1)],
            total=3,
            offset=kwargs["offset"],
            limit=kwargs["limit"],
            has_more=True,
        )

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download), 42, offset=2, limit=2)

    assert requested_offsets == [1]
    assert [item.source for item in result.items] == ["task", "task"]
    assert result.total == 4
    assert result.has_more is False


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
        task.definition_key = kwargs["definition_key"]
        from backend.api.models.tasks import TaskLedgerPageRead
        return TaskLedgerPageRead(
            items=[task],
            total=1,
            offset=kwargs["offset"],
            limit=kwargs["limit"],
            has_more=False,
        )

    monkeypatch.setattr(history, "query_ledger", fake_query_ledger)

    result = history.get_media_download_history(_FakeSession(download), 42)

    assert definition_keys == ["download_episode"]
    assert result.total == 1
    assert result.items[0].source == "task"
    assert result.items[0].definition_key == "download_episode"
