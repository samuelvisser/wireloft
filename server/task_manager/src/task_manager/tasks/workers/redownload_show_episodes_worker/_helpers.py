from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.output_template import resolve_episode_output_path
from task_manager.scheduler.db import TaskOperation
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.scheduler.types import OperationSource, OperationStatus
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
    prepare_media_download_artifact,
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


def _selected_download_ids(
        s: Session,
        *,
        show_id: int,
        local_media_profile_id: int | None,
) -> list[int]:
    stmt = (
        select(EpisodeMediaDownload.id)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(Episode.show_id == show_id)
    )
    if local_media_profile_id is not None:
        stmt = stmt.where(
            EpisodeMediaDownload.local_media_profile_id == local_media_profile_id,
        )
    return list(s.scalars(stmt.order_by(EpisodeMediaDownload.id.asc())))


def _selected_local_media_profile_count(
        s: Session,
        media_download_ids: list[int],
) -> int:
    if not media_download_ids:
        return 0
    return len(set(s.scalars(
        select(EpisodeMediaDownload.local_media_profile_id).where(
            EpisodeMediaDownload.id.in_(media_download_ids),
        )
    )))


def _cancel_existing_attempts(
    s: Session,
    media_download_ids: list[int],
) -> None:
    """Cancel active child operations before destructive replacement starts."""
    operation_ids: set[str] = set()
    for media_download_id in media_download_ids:
        existing = s.get(EpisodeMediaDownload, media_download_id)
        if existing is None:
            continue
        active = get_active_media_download_operation(s, existing.id)
        if active is not None:
            operation_ids.add(active.id)

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
        media_download_ids: list[int],
) -> list[RedownloadTarget]:
    """Reset existing artifacts and create one SYSTEM media.download operation per row."""
    _cancel_existing_attempts(s, media_download_ids)
    prepared: list[RedownloadTarget] = []

    for media_download_id in media_download_ids:
        existing = s.get(EpisodeMediaDownload, media_download_id)
        if existing is None:
            continue
        episode = existing.media
        if not isinstance(episode, Episode):
            continue

        is_redownload = (
            existing.downloaded_at is not None
            or existing.artifact_status in {
                MediaDownloadArtifactStatus.AVAILABLE.value,
                MediaDownloadArtifactStatus.MISSING.value,
                MediaDownloadArtifactStatus.CORRUPTED.value,
            }
        )
        target_path = str(resolve_episode_output_path(
            existing.local_media_profile.output_template,
            episode=episode,
        ))
        prepare_media_download_artifact(existing)
        existing.file_path = target_path
        s.flush()

        operation = create_media_download_operation(
            s,
            existing,
            source=OperationSource.SYSTEM.value,
            is_redownload=is_redownload,
        )
        prepared.append(RedownloadTarget(
            media_download_id=existing.id,
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
