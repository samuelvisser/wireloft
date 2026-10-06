from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, event, func, select
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
from dailywire_downloader.storage.artifacts import remove_download_artifacts
from config import get_settings
from task_manager.scheduler.db import (
    TaskDefinition,
    TaskOperation,
    TaskOperationRun,
    TaskOperationTarget,
    TaskRun,
)
from task_manager.scheduler.operation_control import (
    cancel_operation as cancel_task_operation,
    restart_operation as restart_task_operation,
)
from task_manager.scheduler.operations import (
    OperationDependencySpec,
    OperationTargetSpec,
    add_operation_dependencies,
    clear_operation_admission_wait,
    create_operation,
    link_run_to_operations,
    operation_admission_wait_state,
    operation_target_needs_dispatch,
    refresh_operation,
    set_operation_admission_wait,
)
from task_manager.scheduler.transactional import queue_task_after_commit
from task_manager.scheduler.types import (
    OperationDependencyCancelPolicy,
    OperationSource,
    OperationStatus,
    ResourceType,
    TaskStatus,
)
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


logger = logging.getLogger(__name__)
MEDIA_DOWNLOAD_OPERATION_KIND = "media.download"
MEDIA_DOWNLOAD_PUBLICATION_DELAY_REASON = "publication_delay"
MEDIA_DOWNLOAD_PUBLICATION_DELAY_MESSAGE = "Waiting for the post-publication download delay"
_PUBLICATION_DELAY_BYPASSED_CONTEXT_KEY = "publication_delay_bypassed"
_DOWNLOAD_TASK_KEYS = ("download_episode", "download_movie")
_DELAY_DISPATCH_JOB_PREFIX = "media-download-delay"
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

# The queue budget and its durable TaskRun reservations must be one serialized
# transaction. Without this guard, two dispatcher sessions can both observe five
# free slots and each reserve five before either transaction commits.
_DOWNLOAD_DISPATCH_LOCK = threading.Lock()
_DOWNLOAD_DISPATCH_TRANSACTION_KEY = "wireloft.media_download_dispatch_transaction"


def _hold_download_dispatch_lock_until_transaction_end(session: Session) -> None:
    """Serialize queue budget calculation through the reservation commit."""
    current_transaction = session.get_transaction()
    held_transaction = session.info.get(_DOWNLOAD_DISPATCH_TRANSACTION_KEY)
    if held_transaction is current_transaction and held_transaction is not None:
        return
    if held_transaction is not None:
        raise RuntimeError("Download dispatch lock is already held by another transaction")

    if current_transaction is None:
        session.begin()
        current_transaction = session.get_transaction()
    assert current_transaction is not None

    _DOWNLOAD_DISPATCH_LOCK.acquire()
    session.info[_DOWNLOAD_DISPATCH_TRANSACTION_KEY] = current_transaction


@event.listens_for(Session, "after_transaction_end")
def _release_download_dispatch_lock(session: Session, transaction) -> None:
    if session.info.get(_DOWNLOAD_DISPATCH_TRANSACTION_KEY) is not transaction:
        return
    session.info.pop(_DOWNLOAD_DISPATCH_TRANSACTION_KEY, None)
    _DOWNLOAD_DISPATCH_LOCK.release()


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
        remove_download_artifacts(removed_path, sidecar_paths=tuple(asset.path for asset in download.assets))
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
    download.assets.clear()
    if isinstance(download, EpisodeMediaDownload):
        download.downloaded_publish_status = None


def _task_key(download: MediaDownloadBase) -> str:
    if download.type in {MediaType.MOVIE.value, MediaType.MOVIE_EXTRA.value}:
        return "download_movie"
    return "download_episode"


def _operation_context(
    download: MediaDownloadBase,
    *,
    is_redownload: bool,
    prepare_existing_artifact: bool,
) -> dict:
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
        "nfo_path": download.nfo_path,
        "episode_slug": episode.slug if episode else None,
        "episode_title": episode.title if episode else None,
        "episode_identifier": episode.episode_identifier if episode else None,
        "show_slug": show.slug if show else None,
        "show_title": show.title if show else None,
        "movie_slug": movie.slug if movie else None,
        "movie_title": movie.title if movie else None,
        "movie_extra_type": movie_extra.movie_extra_type if movie_extra else None,
        "is_redownload": bool(is_redownload),
        "prepare_existing_artifact": bool(prepare_existing_artifact),
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
            func.coalesce(TaskOperation.context["cancel_requested"].as_boolean(), False).is_(False),
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
    source: str = OperationSource.SYSTEM,
    is_redownload: bool = False,
    prepare_existing_artifact: bool | None = None,
    not_before: datetime | None = None,
) -> TaskOperation:
    """Create the canonical execution operation for one MediaDownload attempt.

    UI-sourced operations represent an explicit download-button click and are
    automatically prioritized over background/profile work. If automatic work
    already queued the same MediaDownload, the user click promotes that existing
    operation rather than creating a duplicate attempt.
    """
    existing = get_active_media_download_operation(session, download.id)
    if existing is not None:
        # Explicit requests bypass an automatic post-publication admission wait.
        # They still reuse the same operation so one artifact cannot gain two
        # concurrent attempts merely because the user clicked Download.
        if source != OperationSource.SYSTEM:
            existing.context = {
                **(existing.context or {}),
                _PUBLICATION_DELAY_BYPASSED_CONTEXT_KEY: True,
            }
            clear_operation_admission_wait(existing)
            refresh_operation(session, existing.id)
            if existing.status == OperationStatus.QUEUED.value:
                _prioritize_queued_operation(session, existing)
        elif (
            not (
                isinstance(existing.context, dict)
                and existing.context.get(_PUBLICATION_DELAY_BYPASSED_CONTEXT_KEY) is True
            )
            and existing.targets
            and operation_target_needs_dispatch(
                session,
                existing.id,
                existing.targets[0].slot_key,
            )
        ):
            if not_before is not None and not_before > datetime.now(timezone.utc):
                set_operation_admission_wait(
                    existing,
                    reason=MEDIA_DOWNLOAD_PUBLICATION_DELAY_REASON,
                    message=MEDIA_DOWNLOAD_PUBLICATION_DELAY_MESSAGE,
                    until=not_before,
                )
            else:
                clear_operation_admission_wait(existing)
            refresh_operation(session, existing.id)
        return existing

    should_prepare_existing = (
        bool(is_redownload)
        if prepare_existing_artifact is None
        else bool(prepare_existing_artifact)
    )
    target = OperationTargetSpec(
        task_key=_task_key(download),
        resource_type="media_download",
        resource_id=download.id,
        task_kwargs={
            "is_redownload": bool(is_redownload),
            "prepare_existing_artifact": should_prepare_existing,
        },
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
        context=_operation_context(
            download,
            is_redownload=is_redownload,
            prepare_existing_artifact=should_prepare_existing,
        ),
    )
    if (
        source == OperationSource.SYSTEM.value
        and not_before is not None
        and not_before > datetime.now(timezone.utc)
    ):
        set_operation_admission_wait(
            operation,
            reason=MEDIA_DOWNLOAD_PUBLICATION_DELAY_REASON,
            message=MEDIA_DOWNLOAD_PUBLICATION_DELAY_MESSAGE,
            until=not_before,
        )
        refresh_operation(session, operation.id)
    record_media_download_history(
        session,
        download.id,
        MediaDownloadHistoryAction.QUEUED,
        metadata={
            "operation_id": operation.id,
            "source": source,
            "is_redownload": bool(is_redownload),
            **(
                {"publication_delay_not_before": not_before.isoformat()}
                if not_before is not None
                else {}
            ),
        },
    )
    if (
        source == OperationSource.UI.value
        and operation.status == OperationStatus.QUEUED.value
    ):
        _prioritize_queued_operation(session, operation)
    session.flush()
    return operation


def set_media_download_operation_not_before(
    session: Session,
    media_download_id: int,
    not_before: datetime | None,
) -> TaskOperation | None:
    """Synchronize an automatic operation's pre-execution publication wait.

    Only SYSTEM operations without a TaskRun reservation are mutable here.
    Explicit UI/API work bypasses the automatic delay, and an operation that has
    already claimed a download slot must never be moved back behind admission.
    """
    operation = get_active_media_download_operation(session, media_download_id)
    if operation is None or operation.source != OperationSource.SYSTEM.value:
        return operation
    if (
        isinstance(operation.context, dict)
        and operation.context.get(_PUBLICATION_DELAY_BYPASSED_CONTEXT_KEY) is True
    ):
        return operation
    if not operation.targets:
        return operation

    target = operation.targets[0]
    if not operation_target_needs_dispatch(session, operation.id, target.slot_key):
        return operation

    if not_before is not None and not_before > datetime.now(timezone.utc):
        set_operation_admission_wait(
            operation,
            reason=MEDIA_DOWNLOAD_PUBLICATION_DELAY_REASON,
            message=MEDIA_DOWNLOAD_PUBLICATION_DELAY_MESSAGE,
            until=not_before,
        )
    else:
        clear_operation_admission_wait(operation)

    refresh_operation(session, operation.id)
    session.flush()
    return operation


def attach_redownload_dependencies(
        session: Session,
        parent_operation: TaskOperation,
        downloads: list[MediaDownloadBase] | tuple[MediaDownloadBase, ...],
) -> tuple[TaskOperation, ...]:
    """Attach one independently visible media.download operation per artifact.

    Captured byte weights are frozen before any child begins destructive
    preparation. Existing active downloads are observed without ownership;
    newly created children may be canceled with the parent while exclusive.
    """
    unique_downloads = list({download.id: download for download in downloads}.values())
    if not unique_downloads:
        return ()

    sizes = {
        download.id: next(
            (
                int(size)
                for size in (download.downloaded_bytes, download.artifact_size_bytes)
                if size is not None and size > 0
            ),
            None,
        )
        for download in unique_downloads
    }
    known_sizes = [size for size in sizes.values() if size is not None]
    fallback_size = max(1, sum(known_sizes) // len(known_sizes)) if known_sizes else 1

    children: list[TaskOperation] = []
    dependency_specs: list[OperationDependencySpec] = []
    for download in unique_downloads:
        active = get_active_media_download_operation(session, download.id)
        if active is not None:
            child = active
            cancel_policy = OperationDependencyCancelPolicy.DETACH.value
        else:
            is_redownload = (
                download.downloaded_at is not None
                or download.artifact_status in {
                    MediaDownloadArtifactStatus.AVAILABLE.value,
                    MediaDownloadArtifactStatus.MISSING.value,
                    MediaDownloadArtifactStatus.CORRUPTED.value,
                }
            )
            record_media_download_history(
                session,
                download.id,
                MediaDownloadHistoryAction.RETRY_REQUESTED,
                metadata={
                    "source": OperationSource.SYSTEM.value,
                    "parent_operation_id": parent_operation.id,
                },
            )
            child = create_media_download_operation(
                session,
                download,
                source=OperationSource.SYSTEM.value,
                is_redownload=is_redownload,
                prepare_existing_artifact=True,
            )
            cancel_policy = OperationDependencyCancelPolicy.CANCEL_IF_EXCLUSIVE.value

        weight = sizes.get(download.id) or fallback_size
        dependency_specs.append(OperationDependencySpec(
            child_operation_id=child.id,
            slot_key=f"media_download:{download.id}",
            weight=float(weight),
            required=True,
            cancel_policy=cancel_policy,
            context={
                "media_download_id": download.id,
                "captured_size_bytes": int(weight),
            },
        ))
        children.append(child)

    add_operation_dependencies(
        session,
        parent_operation.id,
        dependency_specs,
    )
    dispatch_queued_media_download_operations(session)
    return tuple(children)


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
    if snapshot is None or snapshot.status != OperationStatus.CANCELED.value:
        return snapshot

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
        if operation_admission_wait_state(operation) is not None:
            operation.context = {
                **(operation.context or {}),
                _PUBLICATION_DELAY_BYPASSED_CONTEXT_KEY: True,
            }
            clear_operation_admission_wait(operation)
            session.commit()
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
    active = session.scalars(
        select(TaskRun)
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(TaskDefinition.key.in_(_DOWNLOAD_TASK_KEYS), TaskRun.status.in_(_ACTIVE_RUN_STATUSES))
    )
    in_flight = sum(
        1 for run in active
        if not ((run.meta or {}).get("_progress_meta", {}).get("download", {}).get("primary_transfer_complete") is True)
    )
    return max(0, int(max_concurrent) - in_flight)



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
        .join(
            TaskOperationTarget,
            TaskOperationTarget.operation_id == TaskOperation.id,
        )
        .where(
            TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
            TaskOperation.status == OperationStatus.QUEUED.value,
        )
        .order_by(
            case((TaskOperation.prioritized_at.is_not(None), 0), else_=1),
            TaskOperation.prioritized_at.asc(),
            TaskOperation.created_at.asc(),
            # Bulk dependency creation can insert many media.download operations
            # inside one transaction. SQLite's server timestamp has only
            # second-level precision, so created_at alone no longer preserves
            # their creation/FIFO order. The target id is monotonic and is the
            # durable creation-order tiebreaker for these one-target operations.
            TaskOperationTarget.id.asc(),
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


def _schedule_delayed_media_download_dispatch(
        operation_id: str,
        *,
        run_at: datetime,
) -> None:
    """Wake the constrained download queue when one admission wait expires."""
    from apscheduler.triggers.date import DateTrigger
    from task_manager.scheduler.scheduler import start_scheduler

    scheduler = start_scheduler()
    scheduler.add_job(
        on_media_download_task_terminal,
        trigger=DateTrigger(run_date=run_at),
        kwargs={"operation_ids": (operation_id,)},
        id=f"{_DELAY_DISPATCH_JOB_PREFIX}-{operation_id}",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=None,
    )


def _refresh_waiting_media_download_operations(session: Session) -> None:
    """Refresh admission waits and recreate their wakeups after restarts."""
    waiting = list(
        session.scalars(
            select(TaskOperation).where(
                TaskOperation.kind == MEDIA_DOWNLOAD_OPERATION_KIND,
                TaskOperation.status == OperationStatus.WAITING.value,
            )
        )
    )
    for operation in waiting:
        wait_state = operation_admission_wait_state(operation)
        if wait_state is None:
            refresh_operation(session, operation.id)
            continue

        until = wait_state.get("until")
        if isinstance(until, (int, float)) and not isinstance(until, bool):
            _schedule_delayed_media_download_dispatch(
                operation.id,
                run_at=datetime.fromtimestamp(float(until), tz=timezone.utc),
            )


def dispatch_queued_media_download_operations(
    session: Session,
    *,
    budget: int | None = None,
) -> int:
    """Reserve queued media.download operations up to the global download limit.

    The configured concurrency limit is a global reservation budget, so the
    budget read and every TaskRun reservation stay serialized until the caller's
    transaction commits. The optional budget is only an additional upper bound;
    it can never override maxConcurrentDownloads.
    """
    _hold_download_dispatch_lock_until_transaction_end(session)
    _refresh_waiting_media_download_operations(session)

    available = remaining_media_download_budget(session)
    effective_budget = available if budget is None else min(max(0, int(budget)), available)
    if effective_budget <= 0:
        return 0

    # Fetch beyond the budget because an older QUEUED operation may already have
    # a committed SCHEDULED reservation. Those operations still count as active
    # in the UI but should not prevent a later truly-unreserved operation from
    # consuming another free slot.
    operations = _ordered_queued_media_download_operations(
        session,
        limit=max(25, effective_budget * 4),
    )

    dispatched = 0
    for operation in operations:
        if _reserve_target_dispatch(session, operation):
            dispatched += 1
            if dispatched >= effective_budget:
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


def on_media_download_transfer_complete() -> None:
    """Release a primary-media lane after its durable transfer-complete snapshot."""
    on_media_download_task_terminal()
