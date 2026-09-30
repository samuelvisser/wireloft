from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


def test_bulk_retry_media_download_operation_uses_one_coordinator_target():
    from backend.api.endpoints.media_downloads.operations import BulkRetryMediaDownloadsOperation

    definition = BulkRetryMediaDownloadsOperation([8, 3, 8])
    targets = definition.targets()

    assert definition.kind == "media_download.bulk_retry"
    assert definition.resource_type == "media_download"
    assert definition.resource_id is None
    assert definition.title == "Downloads"
    assert definition.context() == {"downloads_requested": 2}
    assert definition.media_download_ids == (8, 3)

    assert len(targets) == 1
    assert targets[0].task_key == "media_download_bulk_action_worker"
    assert targets[0].resource_type == "media_download"
    assert targets[0].resource_id is None
    assert targets[0].slot_key == "bulk_retry"
    assert targets[0].task_kwargs == {
        "media_download_ids": [8, 3],
        "action": "retry_bulk",
    }


def test_bulk_cancel_media_download_operation_keeps_per_download_targets():
    from backend.api.endpoints.media_downloads.operations import BulkCancelMediaDownloadsOperation

    definition = BulkCancelMediaDownloadsOperation([8, 3, 8])
    targets = definition.targets()

    assert definition.kind == "media_download.bulk_cancel"
    assert definition.resource_type == "media_download"
    assert definition.resource_id is None
    assert definition.context() == {"downloads_requested": 2}
    assert [target.slot_key for target in targets] == ["media_download:8", "media_download:3"]
    assert all(target.task_key == "media_download_bulk_action_worker" for target in targets)
    assert all(target.resource_type == "media_download" for target in targets)
    assert all(target.resource_id is None for target in targets)
    assert [target.task_kwargs for target in targets] == [
        {"media_download_id": 8, "action": "cancel"},
        {"media_download_id": 3, "action": "cancel"},
    ]


def test_bulk_retry_worker_waits_for_child_download_completion(monkeypatch):
    from task_manager.tasks import download_batch

    targets = [
        download_batch.BatchTarget(1, 8, "Extra", 10, "operation-8", True, True, None),
        download_batch.BatchTarget(2, 3, "Movie", 90, "operation-3", True, True, None),
    ]
    polls = []
    progress_updates: list[tuple[int, str | None]] = []
    monkeypatch.setattr(download_batch, "create_batch_manifest", lambda *args, **kwargs: targets)

    def snapshots(_targets):
        polls.append(True)
        return {
            "operation-8": SimpleNamespace(status="SUCCEEDED", progress_meta=None),
            "operation-3": SimpleNamespace(
                status="RUNNING" if len(polls) == 1 else "SUCCEEDED",
                progress_meta=None,
            ),
        }

    monkeypatch.setattr(download_batch, "_snapshots", snapshots)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(download_batch.asyncio, "sleep", no_sleep)

    class Progress:
        run_id = 1

        def __call__(self) -> bool:
            return False

        def set(self, percent: int, message: str | None = None, *, meta=None) -> None:
            progress_updates.append((percent, message))

    result = asyncio.run(download_batch.run_download_batch([8, 3], progress=Progress()))

    assert len(polls) == 2
    # Captured size weights belong to the durable manifest, not the UI percent.
    assert progress_updates[0][0] == 10
    # The executor publishes terminal 100% after the coordinator returns success.
    assert progress_updates[-1][0] == 99
    assert result.outcome == "succeeded"
    assert result.data == {
        "downloads_requested": 2,
        "downloads_completed": 2,
        "downloads_failed": 0,
        "downloads_canceled": 0,
        "errors": [],
    }


@pytest.mark.parametrize(
    ("kind", "operation_type"),
    [
        ("local_media_profile.redownload_media", "local_media_profile"),
        ("movie.redownload_media", "movie"),
    ],
)
def test_scoped_redownload_operations_use_bulk_retry_coordinator(kind: str, operation_type: str):
    if operation_type == "local_media_profile":
        from backend.api.endpoints.local_media_profiles.operations import LocalMediaProfileRedownloadOperation

        resource = SimpleNamespace(id=11, slug="profile", name="Profile")
        definition = LocalMediaProfileRedownloadOperation(
            resource,
            media_download_ids=[4, 5, 4],
        )
    else:
        from backend.api.endpoints.movies.operations import MovieRedownloadOperation

        resource = SimpleNamespace(id=12, slug="movie", title="Movie")
        definition = MovieRedownloadOperation(
            resource,
            media_download_ids=[4, 5, 4],
        )

    assert definition.kind == kind
    targets = definition.targets()
    assert len(targets) == 1
    assert targets[0].task_kwargs == {
        "media_download_ids": [4, 5],
        "action": "retry_bulk",
    }


def test_weighted_progress_uses_average_known_size_for_unknown_items():
    from task_manager.tasks.helpers.progress import weighted_progress_percent

    # Unknown-size legacy rows should still count, without being treated as a
    # near-zero one-byte item beside a large known download.
    assert weighted_progress_percent([
        (100, 100),
        (0, None),
    ]) == 50
