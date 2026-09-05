from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_types import MediaType
from backend.utils.download_files import remove_download_artifacts
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
from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes


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


def _selected_profiles(
        s: Session,
        *,
        show_id: int,
        download_profile_id: int | None,
) -> list[DownloadProfileBase]:
    stmt = select(DownloadProfileBase).where(DownloadProfileBase.show_id == show_id)
    if download_profile_id is not None:
        stmt = stmt.where(DownloadProfileBase.id == download_profile_id)
    profiles = list(s.scalars(stmt.order_by(DownloadProfileBase.id.asc())))
    if download_profile_id is not None and not profiles:
        raise ValueError("Download Profile is not attached to this show")
    return profiles


def _target_episode_profiles(
        s: Session,
        profiles: list[DownloadProfileBase],
) -> list[tuple[Episode, DownloadProfileBase]]:
    return [
        (episode, profile)
        for profile in profiles
        for episode in get_download_profile_episodes(s, profile)
    ]


def _cancel_existing_attempts(
    s: Session,
    targets: list[tuple[Episode, DownloadProfileBase]],
) -> None:
    """Cancel active child operations before this destructive replacement starts."""
    operation_ids: set[str] = set()
    for episode, profile in targets:
        existing = s.scalar(
            select(EpisodeMediaDownload).where(
                EpisodeMediaDownload.media_item_id == episode.id,
                EpisodeMediaDownload.local_media_profile_id == profile.local_media_profile_id,
            )
        )
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
        targets: list[tuple[Episode, DownloadProfileBase]],
) -> list[RedownloadTarget]:
    """Prepare artifacts and create one SYSTEM media.download operation per target."""
    _cancel_existing_attempts(s, targets)
    prepared: list[RedownloadTarget] = []

    for episode, profile in targets:
        existing = s.scalar(
            select(EpisodeMediaDownload).where(
                EpisodeMediaDownload.media_item_id == episode.id,
                EpisodeMediaDownload.local_media_profile_id == profile.local_media_profile_id,
            )
        )
        target_path = str(resolve_episode_output_path(
            profile.local_media_profile.output_template,
            episode=episode,
        ))

        if existing is None:
            remove_download_artifacts(target_path)
            download = EpisodeMediaDownload(
                type=MediaType.EPISODE.value,
                media_item_id=episode.id,
                local_media_profile_id=profile.local_media_profile_id,
                download_profile_id=profile.id,
                artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
                file_path=target_path,
            )
            s.add(download)
            s.flush()
            is_redownload = False
        else:
            is_redownload = (
                existing.downloaded_at is not None
                or existing.artifact_status in {
                    MediaDownloadArtifactStatus.AVAILABLE.value,
                    MediaDownloadArtifactStatus.MISSING.value,
                    MediaDownloadArtifactStatus.CORRUPTED.value,
                }
            )
            prepare_media_download_artifact(existing)
            existing.download_profile_id = profile.id
            existing.file_path = target_path
            download = existing
            s.flush()

        operation = create_media_download_operation(
            s,
            download,
            source=OperationSource.SYSTEM.value,
            is_redownload=is_redownload,
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
