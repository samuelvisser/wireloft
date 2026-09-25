from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.db.core import get_session
from backend.db.models import Episode, Movie, MovieExtra
from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.types.media_types import MediaType
from backend.services.media_download_history import (
    record_media_download_history,
    record_media_download_operation_history_once,
)
from task_manager.tasks.helpers.downloads.download_files import remove_download_artifacts
from config import get_settings
from task_manager.scheduler.db import TaskDefinition, TaskOperation, TaskOperationRun, TaskRun
from task_manager.scheduler.operation_control import (
    cancel_operation as cancel_task_operation,
    restart_operation as restart_task_operation,
)
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    link_run_to_operations,
    operation_target_needs_dispatch,
)
from task_manager.scheduler.transactional import queue_task_after_commit
from task_manager.scheduler.types import OperationSource, OperationStatus, ResourceType, TaskStatus
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


logger = logging.getLogger(__name__)
MEDIA_DOWNLOAD_OPERATION_KIND = "media.download"
_DOWNLOAD_TASK_KEYS = ("download_episode", "download_movie")
_ACTIVE_OPERATION_STATUSES = (
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
)
_ACTIVE_RUN_STATUSES = (
    TaskStatus.SCHEDULED,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.RETRY_SCHEDULED,
)


def prepare_media_download_artifact(
    session: Session,
    download: MediaDownloadBase,
    *,
    remove_existing_artifacts: bool = True,
) -> None:
    """Prepare domain state for an attempt without encoding any execution state."""
    if remove_existing_artifacts:
        resolved_path = None
        if download.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
            resolved_path = resolve_media_download_file(session, download)
        artifact_status_before_removal = download.artifact_status
        removed_path = str(resolved_path) if resolved_path is not None else download.file_path
        remove_download_artifacts(removed_path, download.thumbnail_path)
        if resolved_path is not None:
            record_media_download_history(
                session,
                download.id,
                MediaDownloadHistoryAction.ARTIFACT_REMOVED,
                metadata={
                    "file_path": removed_path,
                    "previous_artifact_status": artifact_status_before_removal,
                },
            )

    download.artifact_status = MediaDownloadArtifactStatus.ABSENT.value
    download.artifact_error = None
    download.artifact_stat_dev = None
    download.artifact_stat_ino = None
    download.artifact_size_bytes = None
    download.artifact_fingerprint = None
    download.automatic_retry_suppressed = False
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.downloaded_at = None
    download.thumbnail_path = None
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
        "thumbnail_path": download.thumbnail_path,
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


def _prioritize_queued_operation(
    session: Session,
    operation: TaskOperation,
) -> TaskOperation:
    """Record queue priority for an operation that has not claimed a slot yet."""
    if not operation.targets:
        raise ValueError("This queued download has no executable target")
    target = operation.targets[0]
    if not operation_target_needs_dispatch(session, operation.id, target.slot_key):
        # It can still be presented as QUEUED while its SCHEDULED TaskRun is
        # waiting for a worker thread. At that point the download already owns a
        # slot, so there is no remaining queue position to change.
        return operation

    operation.prioritized_at = datetime.now(timezone.utc)
    if operation.resource_id is not None:
        record_media_download_history(
            session,
            int(operation.resource_id),
            MediaDownloadHistoryAction.PRIORITIZED,
            metadata={"operation_id": operation.id},
            occurred_at=operation.prioritized_at,
        )
    session.flush()
    return operation


def prioritize_media_download_operation(
    session: Session,
    media_download_id: int,
) -> TaskOperation:
    """Move one queued media download ahead of the ordinary FIFO queue.

    Priority itself remains FIFO: each click records a fresh UTC timestamp, so
    downloads prioritized earlier are selected before downloads prioritized
    later. Re-prioritizing the same download deliberately moves it to the end of
    the prioritized group.
    """
    operation = get_active_media_download_operation(session, media_download_id)
    if operation is None or operation.status != OperationStatus.QUEUED.value:
        raise ValueError("This download is not queued")

    return _prioritize_queued_operation(session, operation)


def create_media_download_operation(
    session: Session,
    download: MediaDownloadBase,
    *,
    source: str = OperationSource.SYSTEM.value,
    is_redownload: bool = False,
) -> TaskOperation:
    """Create the canonical execution operation for one MediaDownload attempt.

    UI-sourced operations represent an explicit download-button click and are
    automatically prioritized over background/profile work. If automatic work
    already queued the same MediaDownload, the user click promotes that existing
    operation rather than creating a duplicate attempt.
    """
    existing = get_active_media_download_operation(session, download.id)
    if existing is not None:
        if (
            source == OperationSource.UI.value
            and existing.status == OperationStatus.QUEUED.value
        ):
            _prioritize_queued_operation(session, existing)
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
    record_media_download_history(
        session,
        download.id,
        MediaDownloadHistoryAction.QUEUED,
        metadata={
            "operation_id": operation.id,
            "source": source,
            "is_redownload": bool(is_redownload),
        },
    )
    if (
        source == OperationSource.UI.value
        and operation.status == OperationStatus.QUEUED.value
    ):
        _prioritize_queued_operation(session, operation)
    session.flush()
    return operation


def _get_media_download_operation(
    session: Session,
    operation_id: str,
) -> TaskOperation | None:
    operation = session.get(TaskOperation, operation_id)
    if operation is None:
        return None
    if (
        operation.kind != MEDIA_DOWNLOAD_OPERATION_KIND
        or operation.resource_type != "media_download"
        or operation.resource_id is None
    ):
        raise ValueError("Operation is not a media download")
    return operation


def _history_metadata_for_operation(
    session: Session,
    operation: TaskOperation,
) -> dict:
    context = operation.context if isinstance(operation.context, dict) else {}
    task_run_id = session.scalar(
        select(func.max(TaskOperationRun.task_run_id))
        .where(TaskOperationRun.operation_id == operation.id)
    )
    metadata = {
        "operation_id": operation.id,
        "source": operation.source,
        "is_redownload": bool(context.get("is_redownload")),
    }
    if task_run_id is not None:
        metadata["task_run_id"] = int(task_run_id)
    return metadata


def cancel_media_download_operation(
    operation_id: str,
    *,
    reason: str = "Canceled by user",
    acknowledge: bool = True,
):
    """Cancel any media.download operation and durably mirror that action to history."""
    session = get_session()
    try:
        operation = _get_media_download_operation(session, operation_id)
        if operation is None:
            return None
        media_download_id = int(operation.resource_id)
        metadata = {
            **_history_metadata_for_operation(session, operation),
            "reason": reason,
        }
        record_media_download_operation_history_once(
            session,
            media_download_id,
            MediaDownloadHistoryAction.CANCEL_REQUESTED,
            operation_ids=(operation.id,),
            metadata=metadata,
        )
        session.commit()
    finally:
        session.close()

    snapshot = cancel_task_operation(
        operation_id,
        reason=reason,
        acknowledge=acknowledge,
    )
    if snapshot is None:
        return None

    session = get_session()
    try:
        metadata = {
            **metadata,
            "operation_id": snapshot.id,
            "source": snapshot.source,
            "is_redownload": bool(
                snapshot.context.get("is_redownload")
                if isinstance(snapshot.context, dict)
                else False
            ),
            "reason": reason,
        }
        if snapshot.started_at is not None and snapshot.finished_at is not None:
            metadata["duration_ms"] = max(
                0,
                int((snapshot.finished_at - snapshot.started_at).total_seconds() * 1000),
            )
        record_media_download_operation_history_once(
            session,
            media_download_id,
            MediaDownloadHistoryAction.CANCELLED,
            operation_ids=(snapshot.id,),
            metadata=metadata,
            occurred_at=snapshot.finished_at,
        )
        session.commit()
    finally:
        session.close()
    return snapshot


def restart_media_download_operation(operation_id: str):
    """Restart a media.download operation while retaining the restart in domain history."""
    session = get_session()
    try:
        operation = _get_media_download_operation(session, operation_id)
        if operation is None:
            return None
        media_download_id = int(operation.resource_id)
        was_active = operation.status in _ACTIVE_OPERATION_STATUSES
        metadata = _history_metadata_for_operation(session, operation)
    finally:
        session.close()

    snapshot = restart_task_operation(operation_id)
    if snapshot is None:
        return None

    session = get_session()
    try:
        if was_active:
            reason = "Replaced by restarted operation"
            cancel_metadata = {**metadata, "reason": reason}
            record_media_download_operation_history_once(
                session,
                media_download_id,
                MediaDownloadHistoryAction.CANCEL_REQUESTED,
                operation_ids=(operation_id,),
                metadata=cancel_metadata,
            )
            record_media_download_operation_history_once(
                session,
                media_download_id,
                MediaDownloadHistoryAction.CANCELLED,
                operation_ids=(operation_id,),
                metadata=cancel_metadata,
            )

        record_media_download_history(
            session,
            media_download_id,
            MediaDownloadHistoryAction.RESTARTED,
            metadata={
                "operation_id": snapshot.id,
                "source": snapshot.source,
                "is_redownload": bool(
                    snapshot.context.get("is_redownload")
                    if isinstance(snapshot.context, dict)
                    else False
                ),
            },
            occurred_at=snapshot.updated_at,
        )
        session.commit()
    finally:
        session.close()
    return snapshot


def record_interrupted_media_download_run_history(
    session: Session,
    interrupted_runs: list[TaskRun],
    *,
    occurred_at: datetime,
) -> int:
    """Record download attempts that were still running when WireLoft stopped."""
    download_definition_ids = set(
        session.scalars(
            select(TaskDefinition.id).where(TaskDefinition.key.in_(_DOWNLOAD_TASK_KEYS))
        )
    )
    if not download_definition_ids:
        return 0

    running_runs = [
        run
        for run in interrupted_runs
        if (
            run.status == TaskStatus.RUNNING
            and run.definition_id in download_definition_ids
            and run.resource_type == ResourceType.MEDIA_DOWNLOAD
            and run.resource_id is not None
        )
    ]
    if not running_runs:
        return 0

    operation_ids_by_run: dict[int, list[str]] = {}
    running_run_ids = [run.id for run in running_runs]
    for task_run_id, operation_id in session.execute(
        select(TaskOperationRun.task_run_id, TaskOperationRun.operation_id)
        .join(TaskOperation, TaskOperation.id == TaskOperationRun.operation_id)
        .where(
            TaskOperationRun.task_run_id.in_(running_run_ids),
            TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
        )
    ):
        operation_ids_by_run.setdefault(int(task_run_id), []).append(str(operation_id))

    recorded = 0
    for run in running_runs:
        inputs = run.meta.get("inputs") if isinstance(run.meta, dict) else None
        metadata = {
            "task_run_id": int(run.id),
            "is_redownload": bool(
                inputs.get("is_redownload")
                if isinstance(inputs, dict)
                else False
            ),
            "reason": "Canceled due to premature shutdown",
        }
        if run.started_at is not None:
            metadata["duration_ms"] = max(
                0,
                int((occurred_at - run.started_at).total_seconds() * 1000),
            )

        if record_media_download_operation_history_once(
            session,
            int(run.resource_id),
            MediaDownloadHistoryAction.INTERRUPTED,
            operation_ids=tuple(operation_ids_by_run.get(run.id, ())),
            metadata=metadata,
            occurred_at=occurred_at,
        ) is not None:
            recorded += 1

    return recorded


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
    # Priority is consumed once the operation has claimed a download slot. This
    # prevents an old click from affecting a later recovery of the same operation.
    operation.prioritized_at = None
    return True


def _ordered_queued_media_download_operations(
    session: Session,
    *,
    limit: int | None = None,
) -> list[TaskOperation]:
    """Return queued downloads in the exact order used by the dispatcher."""
    stmt = (
        select(TaskOperation)
        .where(
            TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
            TaskOperation.status == OperationStatus.QUEUED.value,
        )
        .order_by(
            case((TaskOperation.prioritized_at.is_not(None), 0), else_=1),
            TaskOperation.prioritized_at.asc(),
            TaskOperation.created_at.asc(),
            TaskOperation.id.asc(),
        )
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def get_media_download_queue_positions(session: Session) -> dict[int, int]:
    """Return 1-based positions for downloads still waiting to claim a slot.

    Operations that already own a SCHEDULED/active TaskRun are omitted because
    they are no longer candidates for the next dispatcher slot, even if their
    aggregate operation is briefly still presented as QUEUED.
    """
    positions: dict[int, int] = {}
    for operation in _ordered_queued_media_download_operations(session):
        if not operation.targets:
            continue
        target = operation.targets[0]
        if not operation_target_needs_dispatch(session, operation.id, target.slot_key):
            continue
        if operation.resource_id is None:
            continue
        positions[int(operation.resource_id)] = len(positions) + 1
    return positions


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
    operations = _ordered_queued_media_download_operations(
        session,
        limit=max(25, budget * 4),
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
