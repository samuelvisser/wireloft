from __future__ import annotations

import asyncio

from dailywire_downloader import DownloadCancelled
from sqlalchemy import select

from backend.services.download_actions import (
    cancel_media_download_action,
    delete_media_download_artifact_action,
    retry_media_download_action,
)
from backend.db.core import get_session
from backend.db.models.media_download import MediaDownloadBase
from task_manager.scheduler.operations import get_operation
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult
from task_manager.scheduler.types import OperationSource, OperationStatus
from task_manager.tasks.download_batch import run_download_batch
from task_manager.tasks.media_download_operations import cancel_media_download_operation


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
        ids = media_download_ids or []
        return await run_download_batch(ids, progress=progress)

    if media_download_id is None:
        raise ValueError(f"Bulk media download action '{action}' requires media_download_id")

    if action == "retry":
        return await run_download_batch([media_download_id], progress=progress)

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
