from __future__ import annotations

import logging
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
    link_run_to_operations,
    operation_target_needs_dispatch,
)
from task_manager.scheduler.transactional import queue_task_after_commit
from task_manager.scheduler.types import OperationSource, OperationStatus, ResourceType, TaskStatus


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
        # This target belongs to a constrained operation queue. Generic recovery
        # restores it to QUEUED but does not bypass maxConcurrentDownloads by
        # dispatching every interrupted/queued target at once. The task's
        # recovery_dispatcher fills available slots after recovery instead.
        recover_on_restart=False,
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
    session.flush()
    return operation


def remaining_media_download_budget(session: Session) -> int:
    """Return free slots in the single download execution lane.

    SCHEDULED TaskRuns count as reservations. The dispatcher creates those rows
    transactionally before APScheduler receives the jobs, so committed dispatches
    cannot be mistaken for free capacity merely because a worker has not started.
    """
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


def _reserve_target_dispatch(
    session: Session,
    operation: TaskOperation,
) -> bool:
    """Reserve and transactionally dispatch one media.download target.

    Generic TaskOperations normally create TaskRuns when APScheduler starts a
    job. The constrained download lane needs a durable reservation slightly
    earlier so its concurrency accounting remains correct while jobs wait for a
    scheduler thread. The reservation is still an ordinary TaskRun and becomes
    the exact run executed by the generic executor after commit.
    """
    if not operation.targets:
        return False
    target = operation.targets[0]
    if not operation_target_needs_dispatch(session, operation.id, target.slot_key):
        return False

    definition_id = session.scalar(
        select(TaskDefinition.id).where(TaskDefinition.key == target.task_key)
    )
    if definition_id is None:
        raise RuntimeError(f"Task definition '{target.task_key}' is not registered")

    task_kwargs = dict(target.task_kwargs or {})
    run = TaskRun(
        schedule_id=None,
        definition_id=definition_id,
        resource_type=ResourceType.MEDIA_DOWNLOAD,
        resource_id=target.resource_id,
        status=TaskStatus.SCHEDULED,
        progress=0,
        result=None,
        attempt_count=0,
        max_retries=0,
        meta={"inputs": task_kwargs} if task_kwargs else None,
    )
    session.add(run)
    session.flush()
    link_run_to_operations(
        session,
        run=run,
        task_key=target.task_key,
        operation_ids=(operation.id,),
        operation_slot=target.slot_key,
    )

    queue_task_after_commit(
        session,
        def_key=target.task_key,
        resource_type=target.resource_type,
        resource_id=target.resource_id,
        operation_ids=(operation.id,),
        operation_slot=target.slot_key,
        run_id=run.id,
        **task_kwargs,
    )
    return True


def dispatch_queued_media_download_operations(
    session: Session,
    *,
    budget: int | None = None,
) -> int:
    """Reserve queued media.download operations up to the global download limit."""
    if budget is None:
        budget = remaining_media_download_budget(session)
    if budget <= 0:
        return 0

    # Fetch beyond the budget because an older QUEUED operation may already have
    # a committed SCHEDULED reservation. Those operations still count as active
    # in the UI but should not prevent a later truly-unreserved operation from
    # consuming another free slot.
    operations = list(
        session.scalars(
            select(TaskOperation)
            .where(
                TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
                TaskOperation.status == OperationStatus.QUEUED.value,
            )
            .order_by(TaskOperation.created_at.asc(), TaskOperation.id.asc())
            .limit(max(25, budget * 4))
        )
    )

    dispatched = 0
    for operation in operations:
        if _reserve_target_dispatch(session, operation):
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
