from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import (
    Episode,
    LocalMediaProfileBase,
    MovieLocalMediaProfile,
    ShowLocalMediaProfile,
)
from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.local_media_profile_types import LocalMediaProfileType
from backend.types.media_types import MediaType
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
    """Rename every existing episode artifact using one Show Local Media Profile."""
    local_media_profile = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    episode_ids = tuple(s.scalars(
        select(Episode.id)
        .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
        .where(
            EpisodeMediaDownload.local_media_profile_id == local_media_profile.id,
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
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .distinct()
        .order_by(Episode.show_id.asc())
    ))

    operation = create_operation(
        s,
        LocalMediaProfileFileRenameOperation(
            local_media_profile,
            show_ids=show_ids,
        ),
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


def request_movie_local_media_profile_file_rename(
        s: Session,
        local_media_profile: MovieLocalMediaProfile,
) -> dict[str, bool | int | str]:
    download_ids = tuple(s.scalars(
        select(MediaDownloadBase.id)
        .where(
            MediaDownloadBase.local_media_profile_id == local_media_profile.id,
            MediaDownloadBase.type.in_(
                (MediaType.MOVIE.value, MediaType.MOVIE_EXTRA.value)
            ),
            MediaDownloadBase.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .order_by(MediaDownloadBase.id.asc())
    ))

    operation = create_operation(
        s,
        LocalMediaProfileFileRenameOperation(
            local_media_profile,
            movie_profile=True,
        ),
    )
    if not download_ids:
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
        queue_operation_target_dispatch(
            s,
            operation.id,
            f"profile:{local_media_profile.id}",
        )

    s.flush()
    return {
        "queued": bool(download_ids),
        # Retain the existing accepted response contract. For Movie profiles this
        # field represents managed movie/movie-extra artifacts rather than episodes.
        "episodes_queued": len(download_ids),
        "operation_id": operation.id,
    }


def request_local_media_profile_file_rename(
        s: Session,
        local_media_profile_slug: str,
) -> dict[str, bool | int | str]:
    profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    if profile.type == LocalMediaProfileType.SHOW.value:
        return request_show_local_media_profile_file_rename(
            s,
            local_media_profile_slug,
        )
    if profile.type == LocalMediaProfileType.MOVIE.value:
        movie_profile = s.get(MovieLocalMediaProfile, profile.id)
        if movie_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")
        return request_movie_local_media_profile_file_rename(s, movie_profile)

    raise HTTPException(
        status_code=422,
        detail="This Local Media Profile type does not support file renaming",
    )
