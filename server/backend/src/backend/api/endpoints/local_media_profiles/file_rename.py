from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show, ShowLocalMediaProfile
from backend.services.custom_indexes import profile_applies_to_show
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import complete_operation, queue_operation_target_dispatch

from .operations import LocalMediaProfileFileRenameOperation


_PHYSICAL_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)


def request_show_local_media_profile_file_rename(
        s: Session,
        local_media_profile_slug: str,
) -> dict[str, bool | int | str]:
    """Rename every existing episode artifact using one Local Media Profile."""
    local_media_profile = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    applicable_show_ids = tuple(
        show.id for show in s.scalars(select(Show))
        if profile_applies_to_show(local_media_profile, show)
    )
    episode_ids = tuple(s.scalars(
        select(Episode.id)
        .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
        .where(
            EpisodeMediaDownload.local_media_profile_id == local_media_profile.id,
            Episode.show_id.in_(applicable_show_ids),
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .distinct()
        .order_by(Episode.id.asc())
    ))
    show_ids = tuple(s.scalars(
        select(Episode.show_id)
        .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
        .where(
            EpisodeMediaDownload.local_media_profile_id == local_media_profile.id,
            Episode.show_id.in_(applicable_show_ids),
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .distinct()
        .order_by(Episode.show_id.asc())
    ))

    operation = create_operation(
        s,
        LocalMediaProfileFileRenameOperation(local_media_profile, show_ids),
    )
    if not show_ids:
        complete_operation(
            s,
            operation.id,
            summary=f"No existing files use {local_media_profile.name}",
            data={
                "files_renamed": 0,
                "files_unchanged": 0,
                "files_recovered": 0,
                "files_considered": 0,
            },
        )
    else:
        for show_id in show_ids:
            queue_operation_target_dispatch(s, operation.id, f"show:{show_id}")

    s.flush()
    return {
        "queued": bool(episode_ids),
        "episodes_queued": len(episode_ids),
        "operation_id": operation.id,
    }
