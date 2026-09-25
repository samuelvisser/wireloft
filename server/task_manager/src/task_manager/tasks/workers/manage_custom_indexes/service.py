from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.services.custom_indexes import reconcile_show_profile_custom_indexes
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    queue_operation_target_dispatch,
)
from task_manager.scheduler.results import TaskResult
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.helpers.progress import update_progress


_PHYSICAL_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
    MediaDownloadArtifactStatus.MISSING.value,
)


def _queue_followup_rename(
    session: Session,
    *,
    show_id: int,
    local_media_profile_id: int,
) -> str | None:
    has_files = session.scalar(
        select(EpisodeMediaDownload.id)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(
            Episode.show_id == show_id,
            EpisodeMediaDownload.local_media_profile_id == local_media_profile_id,
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .limit(1)
    )
    if has_files is None:
        return None

    target = OperationTargetSpec(
        task_key="rename_show_profile_files",
        resource_type="show",
        resource_id=show_id,
        task_kwargs={"local_media_profile_id": local_media_profile_id},
        slot_key=f"show:{show_id}:profile:{local_media_profile_id}",
    )
    operation = create_operation(
        session,
        kind="local_media_profile.rename_files",
        source=OperationSource.SYSTEM.value,
        resource_type="local_media_profile",
        resource_id=local_media_profile_id,
        title="Rename files after custom indexing",
        targets=[target],
        context={
            "local_media_profile_id": local_media_profile_id,
            "show_id": show_id,
            "custom_index_followup": True,
        },
    )
    queue_operation_target_dispatch(
        session,
        operation.id,
        target.resolved_slot_key(),
    )
    return operation.id


def run_manage_custom_indexes(
    session: Session,
    *,
    show_id: int,
    local_media_profile_id: int,
    rename_after: bool = False,
    progress=None,
) -> TaskResult:
    update_progress(progress, 5, "Checking persistent custom index assignments")
    result = reconcile_show_profile_custom_indexes(
        session,
        show_id=show_id,
        local_media_profile_id=local_media_profile_id,
    )
    session.commit()

    rename_operation_id = None
    if rename_after:
        rename_operation_id = _queue_followup_rename(
            session,
            show_id=show_id,
            local_media_profile_id=local_media_profile_id,
        )
        session.commit()

    update_progress(progress, 100, "Custom index assignments updated")
    return TaskResult(
        summary="Custom index assignments updated",
        data={
            "downloads_considered": result.downloads_considered,
            "assignments_created": result.assignments_created,
            "downloads_changed": len(result.changed_media_download_ids),
            "rename_queued": 1 if rename_operation_id else 0,
        },
    )
