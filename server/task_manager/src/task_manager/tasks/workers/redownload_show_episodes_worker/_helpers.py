from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.utils.output_template import resolve_episode_output_path
from task_manager.scheduler.db import TaskOperation
from task_manager.scheduler.types import OperationSource, OperationStatus
from task_manager.tasks.helpers.progress import weighted_progress_percent
from task_manager.tasks.helpers.downloads.show_episode_downloads import (
    cancel_active_download_attempts,
    delete_episode_download_artifact,
)
from task_manager.tasks.media_download_operations import (
    cancel_media_download_operation,
    create_media_download_operation,
    dispatch_queued_media_download_operations,
)


_POLL_INTERVAL_SECONDS = 0.5
_TERMINAL_CHILD_STATUSES = {
    OperationStatus.SUCCEEDED.value,
    OperationStatus.PARTIAL.value,
    OperationStatus.FAILED.value,
    OperationStatus.CANCELED.value,
}


@dataclass(frozen=True)
class RedownloadTarget:
    media_download_id: int
    operation_id: str
    episode_title: str
    expected_size_bytes: int | None


def _prepare_redownloads(
        s: Session,
        downloads,
) -> list[RedownloadTarget]:
    """Delete selected artifacts and create one replacement media.download operation each."""
    cancel_active_download_attempts(
        s,
        downloads,
        reason="Replaced by show re-download",
    )
    prepared: list[RedownloadTarget] = []

    for download in downloads:
        episode = download.media
        local_media_profile = download.local_media_profile
        target_path = str(resolve_episode_output_path(
            local_media_profile.output_template,
            episode=episode,
            local_media_profile=local_media_profile,
            media_download=download,
        ))

        expected_size_bytes = (
            int(download.downloaded_bytes)
            if download.downloaded_bytes is not None and int(download.downloaded_bytes) > 0
            else int(download.artifact_size_bytes)
            if download.artifact_size_bytes is not None and int(download.artifact_size_bytes) > 0
            else None
        )

        delete_episode_download_artifact(s, download)
        download.file_path = target_path
        s.flush()

        operation = create_media_download_operation(
            s,
            download,
            source=OperationSource.SYSTEM.value,
            is_redownload=True,
        )
        prepared.append(RedownloadTarget(
            media_download_id=download.id,
            operation_id=operation.id,
            episode_title=episode.title,
            expected_size_bytes=expected_size_bytes,
        ))
        # Keep destructive file changes and their durable child operation paired.
        s.commit()

    dispatch_queued_media_download_operations(s)
    s.commit()
    return prepared


def _check_targets(
    s: Session,
    targets: list[RedownloadTarget],
) -> tuple[int, int, str | None]:
    """Return completed count, aggregate percent and first terminal child failure."""
    if not targets:
        return 0, 100, None

    operation_ids = [target.operation_id for target in targets]
    operations = {
        operation.id: operation
        for operation in s.scalars(
            select(TaskOperation).where(TaskOperation.id.in_(operation_ids))
        )
    }

    completed = 0
    progress_by_size: list[tuple[int, int | None]] = []
    failure: str | None = None
    for target in targets:
        operation = operations.get(target.operation_id)
        if operation is None:
            progress_by_size.append((0, target.expected_size_bytes))
            if failure is None:
                failure = f"Download operation for '{target.episode_title}' was removed"
            continue

        operation_progress = max(0, min(100, int(operation.progress or 0)))
        if operation.status == OperationStatus.SUCCEEDED.value:
            completed += 1
            progress_by_size.append((100, target.expected_size_bytes))
            continue

        progress_by_size.append((operation_progress, target.expected_size_bytes))
        if operation.status in _TERMINAL_CHILD_STATUSES and failure is None:
            detail = operation.error or operation.message or operation.status.lower()
            failure = f"Download for '{target.episode_title}' {detail}"

    return completed, weighted_progress_percent(progress_by_size), failure


def _cancel_targets(targets: list[RedownloadTarget], *, reason: str) -> None:
    for target in targets:
        try:
            cancel_media_download_operation(target.operation_id, reason=reason, acknowledge=True)
        except ValueError:
            pass
