from __future__ import annotations

import asyncio

from dailywire_downloader import DownloadCancelled

from backend.api.endpoints.media_downloads.actions import (
    cancel_media_download_action,
    delete_media_download_artifact_action,
    retry_media_download_action,
)
from task_manager.scheduler.operations import get_operation
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult
from task_manager.scheduler.types import OperationSource, OperationStatus
from task_manager.tasks.media_download_operations import cancel_media_download_operation


async def _run_bulk_retry(
        media_download_ids: list[int],
        *,
        progress=None,
) -> TaskResult:
    """Queue replacement downloads and wait for every child operation to finish."""
    ids = list(dict.fromkeys(int(value) for value in media_download_ids))
    if not ids:
        return TaskResult(
            summary="No downloads to retry",
            data={"downloads_requested": 0, "downloads_completed": 0},
        )

    children: list[tuple[int, str]] = []
    try:
        for media_download_id in ids:
            if progress is not None and progress():
                raise DownloadCancelled("Bulk retry was canceled")
            child_operation_id = retry_media_download_action(
                media_download_id,
                source=OperationSource.SYSTEM.value,
                reuse_matching_active=True,
            )
            children.append((media_download_id, child_operation_id))

        while True:
            await asyncio.sleep(0.5)
            if progress is not None and progress():
                raise DownloadCancelled("Bulk retry was canceled")

            completed = 0
            aggregate_progress = 0
            terminal = 0
            failures: list[str] = []

            for media_download_id, operation_id in children:
                operation = get_operation(operation_id)
                if operation is None:
                    terminal += 1
                    failures.append(f"Download {media_download_id} operation disappeared")
                    continue

                status = operation.status
                child_progress = max(0, min(100, int(operation.progress or 0)))
                if status in {
                    OperationStatus.SUCCEEDED.value,
                    OperationStatus.PARTIAL.value,
                    OperationStatus.FAILED.value,
                    OperationStatus.CANCELED.value,
                }:
                    terminal += 1
                    aggregate_progress += 100
                    if status == OperationStatus.SUCCEEDED.value:
                        completed += 1
                    else:
                        detail = operation.error or operation.message or status.lower()
                        failures.append(f"Download {media_download_id}: {detail}")
                else:
                    aggregate_progress += child_progress

            percent = int(aggregate_progress / len(children))
            if progress is not None:
                progress.set(
                    min(99, percent) if terminal < len(children) else 100,
                    f"Completed {completed}/{len(children)} download retries",
                )

            if terminal < len(children):
                continue
            if failures:
                raise RuntimeError("; ".join(failures))

            return TaskResult(
                summary=f"Retry finished: {completed} download{'s' if completed != 1 else ''} completed",
                data={
                    "downloads_requested": len(children),
                    "downloads_completed": completed,
                },
            )
    except Exception:
        for _media_download_id, operation_id in children:
            operation = get_operation(operation_id)
            if operation is None or operation.status not in {
                OperationStatus.QUEUED.value,
                OperationStatus.RUNNING.value,
                OperationStatus.WAITING.value,
            }:
                continue
            try:
                cancel_media_download_operation(
                    operation_id,
                    reason="Parent bulk retry stopped",
                    acknowledge=True,
                )
            except ValueError:
                pass
        raise


@task(
    key="media_download_bulk_action_worker",
    title="Bulk download action",
    description="Coordinates bulk retry, cancel, and artifact deletion actions.",
    allowed_resource_types=("media_download",),
    default_max_retries=0,
    tracks_progress=True,
)
async def media_download_bulk_action_worker(
        *,
        resource_id: int | None = None,
        media_download_id: int | None = None,
        media_download_ids: list[int] | None = None,
        action: str,
        progress=None,
) -> TaskResult:
    """Execute one target of a bulk media-download action."""
    del resource_id  # Bulk targets coordinate work but do not own the MediaDownload row.
    if progress is not None:
        progress.raise_if_cancelled()

    if action == "retry_bulk":
        return await _run_bulk_retry(media_download_ids or [], progress=progress)

    if media_download_id is None:
        raise ValueError(f"Bulk media download action '{action}' requires media_download_id")

    if action == "retry":
        child_operation_id = retry_media_download_action(
            media_download_id,
            source=OperationSource.SYSTEM.value,
            reuse_matching_active=True,
        )
        return TaskResult(
            summary=f"Queued retry for download {media_download_id}",
            data={
                "action": action,
                "media_download_id": media_download_id,
                "download_operation_id": child_operation_id,
            },
        )

    if action == "cancel":
        cancel_media_download_action(
            media_download_id,
            allow_inactive=True,
            missing_ok=True,
        )
        return TaskResult(
            summary=f"Canceled download {media_download_id}",
            data={"action": action, "media_download_id": media_download_id},
        )

    if action == "delete_artifact":
        deleted = delete_media_download_artifact_action(
            media_download_id,
            missing_ok=True,
        )
        return TaskResult(
            summary=(
                f"Deleted artifact for download {media_download_id}"
                if deleted
                else f"Download {media_download_id} no longer exists"
            ),
            data={
                "action": action,
                "media_download_id": media_download_id,
                "files_deleted": 1 if deleted else 0,
            },
        )

    raise ValueError(f"Unsupported bulk media download action: {action}")
