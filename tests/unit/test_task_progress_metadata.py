from __future__ import annotations

from types import SimpleNamespace


def test_download_reporter_preserves_structured_activity_and_selected_format():
    from task_manager.tasks.download_adapter import DownloadProgressReporter
    from dailywire_downloader.lifecycle import DownloadTracker

    calls = []
    class Progress:
        def set(self, percent, message=None, meta=None):
            calls.append((percent, message, meta))

    reporter = DownloadProgressReporter(Progress())
    reporter.selected_format = "1280x720"
    reporter(DownloadTracker().snapshot())
    assert calls[-1][0] == 0
    assert calls[-1][2]["selected_format"] == "1280x720"
    assert calls[-1][2]["download"]["phase"] == "preparing"


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
