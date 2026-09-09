from __future__ import annotations


def test_download_progress_writer_reports_selected_format_as_live_task_metadata():
    from task_manager.scheduler.progress import TASK_RUN_PROGRESS_META_KEY
    from task_manager.tasks.workers.download_episode._helpers import TaskProgressWriter

    calls: list[tuple[int, str | None, dict | None]] = []

    class Progress:
        def set(self, percent: int, message: str | None = None, meta: dict | None = None) -> None:
            calls.append((percent, message, meta))

    writer = TaskProgressWriter(Progress())
    writer.set_selected_format("1280x720")

    assert calls == [
        (0, None, {TASK_RUN_PROGRESS_META_KEY: {"selected_format": "1280x720"}}),
    ]


def test_operations_api_exposes_progress_metadata_only_for_active_single_target_operations(monkeypatch):
    from backend.api.endpoints.operations import service

    operations = [
        {"id": "active", "status": "RUNNING", "progress_total": 1},
        {"id": "multi", "status": "RUNNING", "progress_total": 2},
        {"id": "finished", "status": "SUCCEEDED", "progress_total": 1},
    ]
    requested_ids: list[str] = []

    def live_meta(operation_ids):
        requested_ids.extend(operation_ids)
        return {
            "active": {"selected_format": "1920x1080"},
            "multi": {"selected_format": "1280x720"},
            "finished": {"selected_format": "3840x2160"},
        }

    monkeypatch.setattr(service, "live_operation_progress_meta", live_meta)

    payloads = service._with_progress_meta(operations)

    assert requested_ids == ["active"]
    assert payloads[0]["progress_meta"] == {"selected_format": "1920x1080"}
    assert payloads[1]["progress_meta"] is None
    assert payloads[2]["progress_meta"] is None
