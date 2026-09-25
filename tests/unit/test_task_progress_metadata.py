from __future__ import annotations

from types import SimpleNamespace


def test_download_progress_writer_reports_selected_format_as_standard_progress_metadata():
    from task_manager.tasks.helpers.downloads.engine import TaskProgressWriter

    calls: list[tuple[int, str | None, dict | None]] = []

    class Progress:
        def set(self, percent: int, message: str | None = None, meta: dict | None = None) -> None:
            calls.append((percent, message, meta))

    writer = TaskProgressWriter(Progress())
    writer.set_selected_format("1280x720")

    assert calls == [
        (0, None, {"selected_format": "1280x720"}),
    ]


def _operation(*, status: str, targets: list[object]):
    return SimpleNamespace(
        id="operation",
        kind="media.download",
        source="UI",
        resource_type="media_download",
        resource_id=1,
        title="Download",
        status=status,
        progress=25,
        message="Running",
        result=None,
        context=None,
        error=None,
        notification_seen_at=None,
        started_at=None,
        finished_at=None,
        created_at=None,
        updated_at=None,
        targets=targets,
    )


def _target(run):
    return SimpleNamespace(run_links=[SimpleNamespace(task_run=run)])


def test_task_operation_exposes_progress_metadata_only_for_active_single_target():
    from task_manager.scheduler.operations import (
        TASK_RUN_PROGRESS_META_KEY,
        _operation_snapshot,
    )
    from task_manager.scheduler.types import TaskStatus

    run = SimpleNamespace(
        id=1,
        status=TaskStatus.RUNNING,
        progress=25,
        meta={TASK_RUN_PROGRESS_META_KEY: {"selected_format": "1920x1080"}},
    )
    target = _target(run)

    payload = _operation_snapshot(_operation(status="RUNNING", targets=[target]))
    assert payload.progress_meta == {"selected_format": "1920x1080"}

    finished = _operation_snapshot(_operation(status="SUCCEEDED", targets=[target]))
    assert finished.progress_meta is None

    multi = _operation_snapshot(_operation(status="RUNNING", targets=[target, target]))
    assert multi.progress_meta is None


def test_download_progress_writer_reports_local_processing_phase():
    from task_manager.tasks.helpers.downloads.engine import TaskProgressWriter

    calls: list[tuple[int, str | None, dict | None]] = []

    class Progress:
        def set(self, percent: int, message: str | None = None, meta: dict | None = None) -> None:
            calls.append((percent, message, meta))

    writer = TaskProgressWriter(Progress())
    writer.set_local_processing()

    assert calls == [
        (
            100,
            "Processing downloaded media locally",
            {"download_phase": "local_processing"},
        ),
    ]
