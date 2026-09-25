from __future__ import annotations

from backend.api.endpoints.media_downloads.actions import (
    cancel_media_download_action,
    delete_media_download_artifact_action,
    retry_media_download_action,
)
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult
from task_manager.scheduler.types import OperationSource


@task(
    key="media_download_bulk_action_worker",
    title="Bulk download action",
    description="Applies one Downloads-page bulk action to one selected media download.",
    allowed_resource_types=("media_download",),
    default_max_retries=0,
    tracks_progress=False,
)
async def media_download_bulk_action_worker(
        *,
        resource_id: int | None = None,
        media_download_id: int,
        action: str,
        progress=None,
) -> TaskResult:
    """Execute one target of a filter-scoped bulk download action."""
    del resource_id  # Bulk targets coordinate work but do not own the MediaDownload row.
    if progress is not None:
        progress.raise_if_cancelled()

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
