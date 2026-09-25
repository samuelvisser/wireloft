from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.api.models.show import *
from fastapi import HTTPException

from backend.db.models import Episode, Show
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.utils.episode_download_scope import EpisodeDownloadScope
from task_manager.events.transactional import queue_event
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import (
    complete_operation,
    queue_operation_target_dispatch,
)
from task_manager.tasks.helpers.download_profiles import (
    disable_download_profiles_for_episode_scope,
)

from .events import ShowAdded
from .operations import (
    ShowDeleteDownloadsOperation,
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
_ShowDownloadMaintenanceOperation = ShowDeleteDownloadsOperation | ShowRedownloadOperation


def _select_show_episode_download_scope(
        scope: EpisodeDownloadScope,
        *,
        local_media_profile_id: int | None,
) -> EpisodeDownloadScope:
    """Validate and apply a show action's optional Local Media Profile scope."""
    if not scope.downloads:
        raise HTTPException(status_code=422, detail="This show has no episode downloads")
    if (
        local_media_profile_id is not None
        and local_media_profile_id not in scope.local_media_profile_ids
    ):
        raise HTTPException(
            status_code=422,
            detail="Local Media Profile has no downloads for this show",
        )
    return scope.select(local_media_profile_id=local_media_profile_id)


def _resolve_show_download_maintenance_scope(
        s: Session,
        show_slug: str,
        local_media_profile_id: int | None,
) -> tuple[Show, EpisodeDownloadScope]:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    scope = _select_show_episode_download_scope(
        EpisodeDownloadScope.resolve(s, show_id=show.id),
        local_media_profile_id=local_media_profile_id,
    )
    return show, scope


def _queue_show_download_maintenance(
        s: Session,
        scope: EpisodeDownloadScope,
        operation: _ShowDownloadMaintenanceOperation,
) -> dict[str, bool | int | str]:
    queued_operation = create_operation(s, operation)
    queue_operation_target_dispatch(
        s,
        queued_operation.id,
        queued_operation.targets[0].slot_key,
    )
    return {
        "queued": True,
        "local_media_profiles_queued": scope.local_media_profile_count,
        "operation_id": queued_operation.id,
    }


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
    show = create_database_fields(Show, body)
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


def request_show_download_delete(
        s: Session,
        show_slug: str,
        local_media_profile_id: int | None,
) -> dict[str, bool | int | str]:
    """Disable affected profiles and queue deletion in the same durable transaction."""
    show, scope = _resolve_show_download_maintenance_scope(
        s,
        show_slug,
        local_media_profile_id,
    )

    # Disable before the operation can be dispatched. The router commits these
    # profile changes and the operation atomically, so no newly dispatched delete
    # worker can ever observe the selected profiles still enabled.
    disabled_profile_count = disable_download_profiles_for_episode_scope(s, scope)
    result = _queue_show_download_maintenance(
        s,
        scope,
        ShowDeleteDownloadsOperation(
            show,
            local_media_profile_id=local_media_profile_id,
            selected_profile_count=scope.local_media_profile_count,
            disabled_profile_count=disabled_profile_count,
        ),
    )
    return {
        **result,
        "download_profiles_disabled": disabled_profile_count,
    }


def request_show_episode_redownload(
        s: Session,
        show_slug: str,
        local_media_profile_id: int | None,
) -> dict[str, bool | int | str]:
    """Queue replacement downloads for existing show artifacts in the selected profile scope."""
    show, scope = _resolve_show_download_maintenance_scope(
        s,
        show_slug,
        local_media_profile_id,
    )
    return _queue_show_download_maintenance(
        s,
        scope,
        ShowRedownloadOperation(
            show,
            local_media_profile_id=local_media_profile_id,
            selected_profile_count=scope.local_media_profile_count,
        ),
    )


def request_show_file_rename(
        s: Session,
        show_slug: str,
        local_media_profile_id: int | None,
) -> dict[str, bool | int | str]:
    """Rename existing show artifacts using collision-safe profile-wide plans."""
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    selected_scope = _select_show_episode_download_scope(
        EpisodeDownloadScope.resolve(s, show_id=show.id),
        local_media_profile_id=local_media_profile_id,
    )
    rename_scope = selected_scope.select(artifact_statuses=_PHYSICAL_ARTIFACT_STATUSES)
    profile_ids = rename_scope.local_media_profile_ids

    operation = create_operation(
        s,
        ShowFileRenameOperation(
            show,
            local_media_profile_ids=profile_ids,
        ),
    )
    if not profile_ids:
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
        for profile_id in profile_ids:
            queue_operation_target_dispatch(s, operation.id, f"profile:{profile_id}")

    s.flush()
    return {
        "queued": bool(profile_ids),
        "episodes_queued": len(rename_scope.episode_ids),
        "local_media_profiles_queued": len(profile_ids),
        "operation_id": operation.id,
    }

