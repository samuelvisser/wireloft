from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.download_paths import resolve_unique_episode_download_path
from task_manager.scheduler.db import TaskOperation
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.scheduler.types import OperationSource, OperationStatus
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
    prepare_media_download_artifact,
)
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


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


def _selected_downloads(
        s: Session,
        *,
        show_id: int,
        episode_id: int | None = None,
        local_media_profile_id: int | None = None,
) -> list[EpisodeMediaDownload]:
    """Return existing episode media rows selected for an explicit re-download."""
    stmt = (
        select(EpisodeMediaDownload)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(Episode.show_id == show_id)
    )
    if episode_id is not None:
        stmt = stmt.where(Episode.id == episode_id)
    if local_media_profile_id is not None:
        stmt = stmt.where(
            EpisodeMediaDownload.local_media_profile_id == local_media_profile_id
        )
    return list(s.scalars(stmt.order_by(EpisodeMediaDownload.id.asc())))


def _cancel_existing_attempts(
    s: Session,
    downloads: list[EpisodeMediaDownload],
) -> None:
    """Cancel active child operations before this destructive replacement starts."""
    operation_ids = {
        active.id
        for download in downloads
        for active in (get_active_media_download_operation(s, download.id),)
        if active is not None
    }

    # cancel_operation owns its own short transaction. Drop this session's read
    # transaction first so SQLite never has to upgrade an old snapshot afterwards.
    s.rollback()
    for operation_id in operation_ids:
        try:
            cancel_operation(
                operation_id,
                reason="Replaced by show re-download",
                acknowledge=True,
            )
        except ValueError:
            pass
    s.expire_all()


def _prepare_redownloads(
        s: Session,
        downloads: list[EpisodeMediaDownload],
) -> list[RedownloadTarget]:
    """Replace existing artifacts through one SYSTEM media.download operation each."""
    _cancel_existing_attempts(s, downloads)
    prepared: list[RedownloadTarget] = []

    for download in downloads:
        episode = download.media
        local_media_profile = download.local_media_profile
        target_path = str(resolve_unique_episode_download_path(
            s,
            local_media_profile.output_template,
            episode=episode,
            current_download=download,
        ))

        if download.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
            resolve_media_download_file(
                s,
                download,
                release_read_transaction=True,
            )
        prepare_media_download_artifact(s, download)
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
    progress_total = 0
    for target in targets:
        operation = operations.get(target.operation_id)
        if operation is None:
            return completed, int(progress_total / len(targets)), (
                f"Download operation for '{target.episode_title}' was removed"
            )

        progress_total += max(0, min(100, int(operation.progress or 0)))
        if operation.status == OperationStatus.SUCCEEDED.value:
            completed += 1
            continue
        if operation.status in _TERMINAL_CHILD_STATUSES:
            detail = operation.error or operation.message or operation.status.lower()
            return completed, int(progress_total / len(targets)), (
                f"Download for '{target.episode_title}' {detail}"
            )

    return completed, int(progress_total / len(targets)), None


def _cancel_targets(targets: list[RedownloadTarget], *, reason: str) -> None:
    for target in targets:
        try:
            cancel_operation(target.operation_id, reason=reason, acknowledge=True)
        except ValueError:
            pass
