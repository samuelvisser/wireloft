from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, or_, select

from sqlalchemy.orm import Session

from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.api.models.show import *
from fastapi import HTTPException

from backend.db.models import Episode, Season, Show, ShowLocalMediaProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.episode_types import EpisodePublishStatus
from backend.types.local_media_profile_types import ShowLocalMediaProfileScope
from backend.types.show_types import ShowType
from backend.api.endpoints.media_downloads.service import create_new_episode_download
from config import get_settings
from backend.services.custom_indexes import request_show_custom_index_reconciliation
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
from task_manager.tasks.media_download_operations import attach_redownload_dependencies
from task_manager.scheduler.types import OperationSource

from .events import ShowAdded
from .operations import (
    ShowDeleteDownloadsOperation,
    ShowDownloadAllOperation,
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
        s: Session,
        show: Show,
        *,
        local_media_profile_id: int | None,
        artifact_statuses: tuple[str, ...] | None = None,
) -> EpisodeDownloadScope:
    """Load the selected scope first; validate only if that selection is empty."""
    scope = EpisodeDownloadScope.resolve(
        s,
        show_id=show.id,
        local_media_profile_id=local_media_profile_id,
        artifact_statuses=artifact_statuses,
    )
    if scope.downloads:
        return scope

    show_has_downloads = exists(
        select(EpisodeMediaDownload.id)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(Episode.show_id == show.id)
    )

    # Without an artifact filter, an empty scope already proves the requested
    # profile is empty. Only the broader show-level error still needs resolving.
    if artifact_statuses is None:
        if local_media_profile_id is None:
            raise HTTPException(
                status_code=422,
                detail="This show has no episode downloads",
            )
        if not s.scalar(select(show_has_downloads)):
            raise HTTPException(
                status_code=422,
                detail="This show has no episode downloads",
            )
        raise HTTPException(
            status_code=422,
            detail="Local Media Profile has no downloads for this show",
        )

    # An artifact filter can legitimately produce an empty scope even when the
    # show/profile has downloads. Resolve those validation facts in one fallback
    # statement instead of loading an unfiltered collection.
    if local_media_profile_id is None:
        if not s.scalar(select(show_has_downloads)):
            raise HTTPException(
                status_code=422,
                detail="This show has no episode downloads",
            )
        return scope

    profile_has_downloads = exists(
        select(EpisodeMediaDownload.id)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(
            Episode.show_id == show.id,
            EpisodeMediaDownload.local_media_profile_id
            == local_media_profile_id,
        )
    )
    has_show_downloads, has_profile_downloads = s.execute(
        select(show_has_downloads, profile_has_downloads)
    ).one()
    if not has_show_downloads:
        raise HTTPException(
            status_code=422,
            detail="This show has no episode downloads",
        )
    if not has_profile_downloads:
        raise HTTPException(
            status_code=422,
            detail="Local Media Profile has no downloads for this show",
        )
    return scope


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
        s,
        show,
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
    request_show_custom_index_reconciliation(s, show.id)

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


def request_show_download_all(
        s: Session,
        show_slug: str,
        body: ShowDownloadAllAPIRequest,
) -> dict[str, bool | int | str]:
    """Download indexed, published episodes for one profile without replacing available files."""
    show = s.scalar(select(Show).where(Show.slug == show_slug))
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    profile = s.get(ShowLocalMediaProfile, body.local_media_profile_id)
    if profile is None:
        raise HTTPException(status_code=422, detail="Select a Show Local Media Profile")
    if profile.show_scope not in (ShowLocalMediaProfileScope.BOTH, show.type):
        raise HTTPException(status_code=422, detail="Local Media Profile is not available for this show type")

    if not body.episode_types:
        raise HTTPException(status_code=422, detail="Select at least one episode type")
    published_at = func.coalesce(Episode.published_date, Episode.went_live_date)
    statement = select(Episode).where(
        Episode.show_id == show.id,
        Episode.publish_status.in_((
            EpisodePublishStatus.PUBLISHED_FINAL,
            EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
        )),
        or_(*(
            Episode.episode_identifier.like(f"{episode_type}.%")
            for episode_type in set(body.episode_types)
        )),
    )
    if show.type == ShowType.SERIES.value:
        if not body.season_ids:
            raise HTTPException(status_code=422, detail="Select at least one season")
        if body.download_days_in_past or body.download_episode_count or body.download_starting_from:
            raise HTTPException(status_code=422, detail="Podcast limits cannot be used for series")
        selected_ids = set(body.season_ids)
        valid_ids = set(s.scalars(
            select(Season.id).where(Season.show_id == show.id, Season.id.in_(selected_ids))
        ))
        if selected_ids != valid_ids:
            raise HTTPException(status_code=422, detail="A selected season does not belong to this show")
        statement = (
            statement.where(Episode.season_id.in_(selected_ids))
            .order_by(Episode.season_id.asc(), Episode.index.asc(), Episode.id.asc())
        )
    else:
        if body.season_ids:
            raise HTTPException(status_code=422, detail="Podcast downloads cannot filter by season")
        if body.download_days_in_past:
            cutoff = datetime.now(timezone.utc) - timedelta(days=body.download_days_in_past)
            statement = statement.where(or_(published_at.is_(None), published_at >= cutoff))
        elif body.download_starting_from is not None:
            local_start = datetime.combine(
                body.download_starting_from, time.min,
                tzinfo=ZoneInfo(get_settings().timezone),
            )
            statement = statement.where(
                published_at.is_not(None),
                published_at >= local_start.astimezone(timezone.utc),
            )
        statement = statement.order_by(published_at.desc(), Episode.id.desc())
        if body.download_episode_count:
            statement = statement.limit(body.download_episode_count)

    episodes = list(s.scalars(statement))
    existing_by_episode = {
        download.media_item_id: download
        for download in s.scalars(
            select(EpisodeMediaDownload).where(
                EpisodeMediaDownload.local_media_profile_id == profile.id,
                EpisodeMediaDownload.media_item_id.in_([episode.id for episode in episodes]),
            )
        )
    }
    downloads: list[EpisodeMediaDownload] = []
    for episode in episodes:
        download = existing_by_episode.get(episode.id)
        if download is not None and download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
            continue
        if download is None:
            download = create_new_episode_download(s, episode, profile)
        downloads.append(download)

    operation = create_operation(
        s,
        ShowDownloadAllOperation(
            show,
            local_media_profile_id=profile.id,
            download_count=len(downloads),
        ),
    )
    if downloads:
        attach_redownload_dependencies(
            s, operation, tuple(downloads),
            source=OperationSource.SYSTEM.value,
            respect_episode_publication=True,
        )
    else:
        complete_operation(
            s,
            operation.id,
            summary=f"No new episodes to download for {show.title}",
            data={"downloads_completed": 0},
        )

    s.flush()
    return {
        "queued": bool(downloads),
        "episodes_queued": len(downloads),
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
    scope = scope.select(artifact_statuses=(
        MediaDownloadArtifactStatus.AVAILABLE.value,
        MediaDownloadArtifactStatus.MISSING.value,
        MediaDownloadArtifactStatus.CORRUPTED.value,
    ))
    if not scope.downloads:
        raise HTTPException(
            status_code=422,
            detail="This show has no previously downloaded episode media in the selected scope",
        )
    operation = create_operation(
        s,
        ShowRedownloadOperation(
            show,
            local_media_profile_id=local_media_profile_id,
            selected_profile_count=scope.local_media_profile_count,
            download_count=len(scope.downloads),
        ),
    )
    attach_redownload_dependencies(s, operation, tuple(scope.downloads))
    s.flush()
    return {
        "queued": True,
        "local_media_profiles_queued": scope.local_media_profile_count,
        "operation_id": operation.id,
    }


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

    rename_scope = _select_show_episode_download_scope(
        s,
        show,
        local_media_profile_id=local_media_profile_id,
        artifact_statuses=_PHYSICAL_ARTIFACT_STATUSES,
    )
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
