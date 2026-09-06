from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields
from backend.api.models.show import *
from fastapi import HTTPException

from backend.db.models import Episode, Show
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.events.transactional import queue_event
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import (
    complete_operation,
    queue_operation_target_dispatch,
)

from .events import ShowAdded
from .operations import (
    ShowFileRenameOperation,
    ShowIndexOperation,
    ShowMetadataRefreshOperation,
    ShowRedownloadOperation,
    ShowSyncOperation,
)


_PHYSICAL_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)


def _show_local_media_profile_ids(s: Session, show_id: int) -> list[int]:
    rows = (
        s.query(EpisodeMediaDownload.local_media_profile_id)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .filter(Episode.show_id == show_id)
        .distinct()
        .order_by(EpisodeMediaDownload.local_media_profile_id.asc())
        .all()
    )
    return [profile_id for (profile_id,) in rows]


def _selected_show_local_media_profiles(
        s: Session,
        *,
        show: Show,
        local_media_profile_id: int | None,
) -> list[int]:
    profile_ids = _show_local_media_profile_ids(s, show.id)
    if not profile_ids:
        raise HTTPException(status_code=422, detail="This show has no episode downloads")
    if local_media_profile_id is None:
        return profile_ids
    if local_media_profile_id not in profile_ids:
        raise HTTPException(
            status_code=422,
            detail="Local Media Profile has no downloads for this show",
        )
    return [local_media_profile_id]


def get_shows_list(s: Session) -> list[ShowAPIRead]:
    shows = (
        s.query(Show)
        .order_by(Show.title.asc())
        .all()
    )
    return [ShowAPIRead.model_validate(show) for show in shows]


def get_show(s: Session, show_slug: str) -> ShowAPIRead:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )

    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    return ShowAPIRead.model_validate(show)


def create_show(s: Session, body: ShowAPICreate) -> ShowAPIRead:
    data = body.model_dump(by_alias=True)

    show = Show(**data)
    s.add(show)
    s.flush()

    create_operation(s, ShowIndexOperation(show))
    queue_event(s, "show.added", ShowAdded(show))

    return ShowAPIRead.model_validate(show)


def update_show(s: Session, show_slug: str, body: ShowAPIUpdate) -> ShowAPIRead:
    show: Optional[Show] = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    update_database_fields(show, body)
    s.flush()

    queue_event(s, "show.updated", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
    })

    return ShowAPIRead.model_validate(show)


def delete_show(s: Session, show_slug: str) -> ShowAPIRead:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    payload = ShowAPIRead.model_validate(show)

    queue_event(s, "show.deleted", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
    })

    s.delete(show)
    s.flush()

    return payload


def request_show_sync(s: Session, show_slug: str) -> dict[str, bool | str]:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    operation = create_operation(s, ShowSyncOperation(show))
    queue_operation_target_dispatch(s, operation.id, operation.targets[0].slot_key)
    return {"queued": True, "operation_id": operation.id}


def request_show_metadata_refresh(
        s: Session,
        show_slug: str,
) -> dict[str, bool | int | str]:
    """Queue the normal metadata refresh flow for every episode in one show."""
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    episodes = (
        s.query(Episode)
        .filter_by(show_id=show.id)
        .all()
    )
    operation = create_operation(
        s,
        ShowMetadataRefreshOperation(show, episodes),
    )

    if not episodes:
        complete_operation(
            s,
            operation.id,
            summary=f"No episodes to refresh in {show.title}",
            data={"episodes_refreshed": 0, "episodes_requested": 0},
        )
    else:
        for episode in episodes:
            if queue_operation_target_dispatch(s, operation.id, f"episode:{episode.id}"):
                episode.metadata_is_final = False

    s.flush()
    return {
        "queued": bool(episodes),
        "episodes_queued": len(episodes),
        "operation_id": operation.id,
    }


def request_show_file_rename(
        s: Session,
        show_slug: str,
        local_media_profile_id: int | None,
) -> dict[str, bool | int | str]:
    """Rename existing show artifacts for one or every Local Media Profile in use."""
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    selected_profile_ids = _selected_show_local_media_profiles(
        s,
        show=show,
        local_media_profile_id=local_media_profile_id,
    )
    episodes = (
        s.query(Episode)
        .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
        .filter(
            Episode.show_id == show.id,
            EpisodeMediaDownload.local_media_profile_id.in_(selected_profile_ids),
            EpisodeMediaDownload.artifact_status.in_(_PHYSICAL_ARTIFACT_STATUSES),
        )
        .distinct()
        .order_by(Episode.id.asc())
        .all()
    )

    operation = create_operation(
        s,
        ShowFileRenameOperation(
            show,
            episodes,
            local_media_profile_id=local_media_profile_id,
            selected_profile_count=len(selected_profile_ids),
        ),
    )
    if not episodes:
        complete_operation(
            s,
            operation.id,
            summary=f"No existing files to rename in {show.title}",
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
        "local_media_profiles_queued": len(selected_profile_ids),
        "operation_id": operation.id,
    }


def request_show_episode_redownload(
        s: Session,
        show_slug: str,
        local_media_profile_id: int | None,
) -> dict[str, bool | int | str]:
    """Queue replacement downloads for existing show artifacts in the selected profile scope."""
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    selected_profile_ids = _selected_show_local_media_profiles(
        s,
        show=show,
        local_media_profile_id=local_media_profile_id,
    )
    operation = create_operation(
        s,
        ShowRedownloadOperation(
            show,
            local_media_profile_id=local_media_profile_id,
            selected_profile_count=len(selected_profile_ids),
        ),
    )
    queue_operation_target_dispatch(s, operation.id, operation.targets[0].slot_key)
    return {
        "queued": True,
        "local_media_profiles_queued": len(selected_profile_ids),
        "operation_id": operation.id,
    }
