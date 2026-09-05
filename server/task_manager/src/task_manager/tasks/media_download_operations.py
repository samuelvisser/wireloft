from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.core import get_session
from backend.db.models import Episode, Movie, MovieExtra
from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_types import MediaType
from backend.utils.download_files import remove_download_artifacts
from config import get_settings
from task_manager.scheduler.db import TaskDefinition, TaskOperation, TaskRun
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    operation_target_needs_dispatch,
    queue_operation_target_dispatch,
)
from task_manager.scheduler.types import OperationSource, OperationStatus, TaskStatus


logger = logging.getLogger(__name__)
MEDIA_DOWNLOAD_OPERATION_KIND = "media.download"
_DOWNLOAD_TASK_KEYS = ("download_episode", "download_movie")
_ACTIVE_OPERATION_STATUSES = (OperationStatus.QUEUED.value, OperationStatus.RUNNING.value)
_ACTIVE_RUN_STATUSES = (
    TaskStatus.SCHEDULED,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.RETRY_SCHEDULED,
)


def prepare_media_download_artifact(
    download: MediaDownloadBase,
    *,
    remove_existing_artifacts: bool = True,
) -> None:
    """Prepare domain state for an attempt without encoding any execution state."""
    if remove_existing_artifacts:
        remove_download_artifacts(download.file_path)
    download.artifact_status = MediaDownloadArtifactStatus.ABSENT.value
    download.artifact_error = None
    download.automatic_retry_suppressed = False
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.downloaded_at = None
    if isinstance(download, EpisodeMediaDownload):
        download.downloaded_publish_status = None


def _task_key(download: MediaDownloadBase) -> str:
    if download.type in {MediaType.MOVIE.value, MediaType.MOVIE_EXTRA.value}:
        return "download_movie"
    return "download_episode"


def _operation_context(download: MediaDownloadBase, *, is_redownload: bool) -> dict:
    media = download.media
    episode = media if isinstance(media, Episode) else None
    movie_extra = media if isinstance(media, MovieExtra) else None
    movie = media if isinstance(media, Movie) else (movie_extra.movie if movie_extra else None)
    show = episode.show if episode else None
    profile = download.local_media_profile

    return {
        "media_download_id": download.id,
        "media_type": download.type,
        "media_item_id": download.media_item_id,
        "media_slug": getattr(media, "slug", None),
        "media_title": getattr(media, "title", None),
        "local_media_profile_id": download.local_media_profile_id,
        "local_media_profile_name": profile.name,
        "preferred_format": profile.preferred_format,
        "file_path": download.file_path,
        "episode_slug": episode.slug if episode else None,
        "episode_title": episode.title if episode else None,
        "episode_identifier": episode.episode_identifier if episode else None,
        "show_slug": show.slug if show else None,
        "show_title": show.title if show else None,
        "movie_slug": movie.slug if movie else None,
        "movie_title": movie.title if movie else None,
        "movie_extra_type": movie_extra.movie_extra_type if movie_extra else None,
        "is_redownload": bool(is_redownload),
    }


def get_active_media_download_operation(
    session: Session,
    media_download_id: int,
) -> Optional[TaskOperation]:
    return session.scalar(
        select(TaskOperation)
        .where(
            TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
            TaskOperation.resource_type == "media_download",
            TaskOperation.resource_id == media_download_id,
            TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
        )
        .order_by(TaskOperation.created_at.desc())
        .limit(1)
    )


def create_media_download_operation(
    session: Session,
    download: MediaDownloadBase,
    *,
    source: str = OperationSource.SYSTEM.value,
    is_redownload: bool = False,
) -> TaskOperation:
    """Create the canonical execution operation for one MediaDownload attempt."""
    existing = get_active_media_download_operation(session, download.id)
    if existing is not None:
        return existing

    target = OperationTargetSpec(
        task_key=_task_key(download),
        resource_type="media_download",
        resource_id=download.id,
        task_kwargs={"is_redownload": bool(is_redownload)},
        slot_key=f"media-download:{download.id}",
    )
    operation = create_operation(
        session,
        kind=MEDIA_DOWNLOAD_OPERATION_KIND,
        source=source,
        resource_type="media_download",
        resource_id=download.id,
        title=getattr(download.media, "title", None) or f"Media download {download.id}",
        targets=[target],
        context=_operation_context(download, is_redownload=is_redownload),
    )
    if source != OperationSource.UI.value:
        # SYSTEM/API operations are visible to the puller while active but do not
        # need a completion toast. Mark the notification side as already handled;
        # active-state relevance is independent of this timestamp.
        operation.notification_seen_at = datetime.now(timezone.utc)
    session.flush()
    return operation


def remaining_media_download_budget(session: Session) -> int:
    max_concurrent = get_settings().download_settings.max_concurrent_downloads
    in_flight = session.scalar(
        select(func.count())
        .select_from(TaskRun)
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(
            TaskDefinition.key.in_(_DOWNLOAD_TASK_KEYS),
            TaskRun.status.in_(_ACTIVE_RUN_STATUSES),
        )
    ) or 0
    return max(0, int(max_concurrent) - int(in_flight))


def dispatch_queued_media_download_operations(
    session: Session,
    *,
    budget: int | None = None,
) -> int:
    """Dispatch queued media.download operations up to the global download limit."""
    if budget is None:
        budget = remaining_media_download_budget(session)
    if budget <= 0:
        return 0

    operations = list(
        session.scalars(
            select(TaskOperation)
            .where(
                TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
                TaskOperation.status == OperationStatus.QUEUED.value,
            )
            .order_by(TaskOperation.created_at.asc(), TaskOperation.id.asc())
            .limit(budget)
        )
    )

    dispatched = 0
    for operation in operations:
        if not operation.targets:
            continue
        target = operation.targets[0]
        if not operation_target_needs_dispatch(session, operation.id, target.slot_key):
            continue
        if queue_operation_target_dispatch(session, operation.id, target.slot_key):
            dispatched += 1
            if dispatched >= budget:
                break
    return dispatched


def on_media_download_task_terminal(**_) -> None:
    """Fill newly freed download slots after a download TaskRun becomes terminal."""
    session = get_session()
    try:
        dispatch_queued_media_download_operations(session)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to dispatch the next queued media download operation")
    finally:
        session.close()
