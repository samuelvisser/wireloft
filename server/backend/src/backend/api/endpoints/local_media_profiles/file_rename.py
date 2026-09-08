from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.db.models import Episode, LocalMediaProfileBase
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.local_media_profile_types import LocalMediaProfileType
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import complete_operation, queue_operation_target_dispatch

from .operations import LocalMediaProfileFileRenameOperation


_PHYSICAL_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)


def request_local_media_profile_file_rename(
        s: Session,
        local_media_profile_slug: str,
) -> dict[str, bool | int | str]:
    """Rename every existing episode artifact using one Local Media Profile."""
    local_media_profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    if local_media_profile.type != LocalMediaProfileType.SHOW.value:
        raise HTTPException(
            status_code=422,
            detail="File Rename currently supports Show Local Media Profiles only",
        )

    episodes = (
        s.query(Episode)
        .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
        .filter(
            EpisodeMediaDownload.local_media_profile_id == local_media_profile.id,
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .distinct()
        .order_by(Episode.id.asc())
        .all()
    )

    operation = create_operation(
        s,
        LocalMediaProfileFileRenameOperation(local_media_profile, episodes),
    )
    if not episodes:
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
        for episode in episodes:
            queue_operation_target_dispatch(s, operation.id, f"episode:{episode.id}")

    s.flush()
    return {
        "queued": bool(episodes),
        "episodes_queued": len(episodes),
        "operation_id": operation.id,
    }
