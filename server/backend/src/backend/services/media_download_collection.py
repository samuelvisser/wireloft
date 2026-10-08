"""Composable SQL for media-download collection status, filtering and ordering.

The helpers in this module build SQLAlchemy expressions and statements rather
than materializing rows. API code remains responsible for cursor validation and
hydrating the small page of ORM objects returned by these queries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Subquery

from backend.db.models import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.db import TaskDefinition, TaskOperation, TaskRun
from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus
from task_manager.tasks.media_download_operations import (
    media_download_queue_position_subquery,
)


_MEDIA_DOWNLOAD_TASK_KEYS = ("download_episode", "download_movie")

_ACTIVE_DOWNLOAD_STATUSES = (
    OperationStatus.QUEUED,
    OperationStatus.RUNNING,
    OperationStatus.WAITING,
)
_ACTIVE_WORKFLOW_STATUSES = (
    "downloading",
    "preparing",
    "waiting",
    "canceling",
    "local_processing",
)
_RETRYABLE_STATUSES = (
    "preparing",
    "waiting",
    "downloading",
    "local_processing",
    "downloaded",
    "redownloaded",
    "error",
    "missing",
    "corrupted",
    "cancelled",
)
_CANCELABLE_STATUSES = (
    "pending",
    "preparing",
    "waiting",
    "downloading",
    "local_processing",
)


def _latest_download_run_ids(
    media_download_ids: Sequence[int] | None = None,
) -> Subquery:
    """Latest download TaskRun IDs, optionally narrowed to one page of downloads."""
    statement = (
        select(
            TaskRun.resource_id.label("media_download_id"),
            func.max(TaskRun.id).label("run_id"),
        )
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(
            TaskRun.resource_type == ResourceType.MEDIA_DOWNLOAD,
            TaskDefinition.key.in_(_MEDIA_DOWNLOAD_TASK_KEYS),
        )
        .group_by(TaskRun.resource_id)
    )
    if media_download_ids is not None:
        statement = statement.where(
            TaskRun.resource_id.in_(media_download_ids)
        )
    return statement.subquery()


def latest_download_runs(
    session: Session,
    media_download_ids: Sequence[int],
) -> dict[int, TaskRun]:
    """Hydrate only the latest TaskRuns needed by one rendered download page."""
    if not media_download_ids:
        return {}

    latest_ids = _latest_download_run_ids(media_download_ids)
    runs = session.scalars(
        select(TaskRun).join(
            latest_ids,
            TaskRun.id == latest_ids.c.run_id,
        )
    )
    return {
        int(run.resource_id): run
        for run in runs
        if run.resource_id is not None
    }


def media_download_queue_positions(
    session: Session,
    media_download_ids: Sequence[int],
) -> dict[int, int]:
    """Read global queue positions only for the downloads being rendered."""
    if not media_download_ids:
        return {}

    queue = media_download_queue_position_subquery()
    return {
        int(media_download_id): int(queue_position)
        for media_download_id, queue_position in session.execute(
            select(
                queue.c.media_download_id,
                queue.c.queue_position,
            )
            .where(queue.c.media_download_id.in_(media_download_ids))
            .order_by(queue.c.queue_position)
        )
    }


def _latest_active_download_operation() -> Subquery:
    """Newest active media.download operation per MediaDownload."""
    ranked = (
        select(
            TaskOperation.resource_id.label("media_download_id"),
            TaskOperation.id.label("operation_id"),
            TaskOperation.status.label("operation_status"),
            TaskOperation.context.label("operation_context"),
            func.row_number().over(
                partition_by=TaskOperation.resource_id,
                order_by=(
                    TaskOperation.created_at.desc(),
                    TaskOperation.id.desc(),
                ),
            ).label("operation_rank"),
        )
        .where(
            TaskOperation.kind == "media.download",
            TaskOperation.resource_type == ResourceType.MEDIA_DOWNLOAD.value,
            TaskOperation.resource_id.is_not(None),
            TaskOperation.status.in_(_ACTIVE_DOWNLOAD_STATUSES),
        )
        .subquery()
    )
    return (
        select(
            ranked.c.media_download_id,
            ranked.c.operation_id,
            ranked.c.operation_status,
            ranked.c.operation_context,
        )
        .where(ranked.c.operation_rank == 1)
        .subquery()
    )


def _download_is_canceling(active_operation, progress_meta, execution):
    return or_(
        func.coalesce(
            active_operation.c.operation_context["cancel_requested"].as_boolean(),
            False,
        ).is_(True),
        func.coalesce(progress_meta["canceling"].as_boolean(), False).is_(True),
        func.coalesce(execution["canceling"].as_boolean(), False).is_(True),
    )


def _main_download_stage_is_waiting(execution):
    stages = func.json_each(
        TaskRun.meta,
        '$."_progress_meta".download.stages',
    ).table_valued("key", "value").alias("download_stage")
    return exists(
        select(stages.c.key).where(
            func.json_extract(stages.c.value, "$.id")
            == execution["main_activity"].as_string(),
            func.json_extract(stages.c.value, "$.wait.reason").is_not(None),
        )
    )


def _download_is_waiting(active_operation, progress_meta, execution):
    return or_(
        active_operation.c.operation_status == OperationStatus.WAITING.value,
        _main_download_stage_is_waiting(execution),
        progress_meta["wait_state"]["reason"].as_string().is_not(None),
    )


def _download_is_transferring(execution):
    return and_(
        execution["phase"].as_string() == "transferring",
        execution["main_activity"].as_string() == "media",
    )


def _download_primary_transfer_is_complete(execution):
    return func.coalesce(
        execution["primary_transfer_complete"].as_boolean(),
        False,
    ).is_(True)


def _download_run_is_redownload():
    return func.coalesce(
        TaskRun.meta["inputs"]["is_redownload"].as_boolean(),
        TaskRun.result["data"]["is_redownload"].as_boolean(),
        False,
    )


def _active_download_status(active_operation, progress_meta, execution):
    """UI status while an active media.download operation owns the download."""
    return case(
        (
            _download_is_canceling(active_operation, progress_meta, execution),
            "canceling",
        ),
        (
            active_operation.c.operation_status == OperationStatus.QUEUED.value,
            "pending",
        ),
        (
            _download_is_waiting(active_operation, progress_meta, execution),
            "waiting",
        ),
        (_download_is_transferring(execution), "downloading"),
        (
            _download_primary_transfer_is_complete(execution),
            "local_processing",
        ),
        else_="preparing",
    )


def _persistent_download_status():
    """UI status when no active media.download operation owns the download."""
    return case(
        (
            MediaDownloadBase.artifact_status
            == MediaDownloadArtifactStatus.AVAILABLE.value,
            case(
                (_download_run_is_redownload().is_(True), "redownloaded"),
                else_="downloaded",
            ),
        ),
        (
            MediaDownloadBase.artifact_status
            == MediaDownloadArtifactStatus.MISSING.value,
            "missing",
        ),
        (
            MediaDownloadBase.artifact_status
            == MediaDownloadArtifactStatus.CORRUPTED.value,
            "corrupted",
        ),
        (TaskRun.status == TaskStatus.RUNNING, "preparing"),
        (TaskRun.status == TaskStatus.FAILED, "error"),
        (
            or_(
                MediaDownloadBase.automatic_retry_suppressed.is_(True),
                TaskRun.status == TaskStatus.CANCELED,
            ),
            "cancelled",
        ),
        else_="not_downloaded",
    )


def _effective_download_status(active_operation):
    progress_meta = TaskRun.meta["_progress_meta"]
    execution = progress_meta["download"]
    return case(
        (
            active_operation.c.operation_id.is_not(None),
            _active_download_status(
                active_operation,
                progress_meta,
                execution,
            ),
        ),
        else_=_persistent_download_status(),
    ).label("status")


def _download_status_source() -> Subquery:
    """One SQL relation containing the effective UI status for every download."""
    latest_run_ids = _latest_download_run_ids()
    active_operation = _latest_active_download_operation()
    queue = media_download_queue_position_subquery()

    return (
        select(
            MediaDownloadBase.id.label("id"),
            MediaDownloadBase.artifact_status.label("artifact_status"),
            MediaDownloadBase.downloaded_at.label("downloaded_at"),
            MediaDownloadBase.created_at.label("created_at"),
            MediaDownloadBase.updated_at.label("updated_at"),
            TaskRun.finished_at.label("run_finished_at"),
            queue.c.queue_position.label("queue_position"),
            _effective_download_status(active_operation),
        )
        .outerjoin(
            latest_run_ids,
            latest_run_ids.c.media_download_id == MediaDownloadBase.id,
        )
        .outerjoin(TaskRun, TaskRun.id == latest_run_ids.c.run_id)
        .outerjoin(
            active_operation,
            active_operation.c.media_download_id == MediaDownloadBase.id,
        )
        .outerjoin(
            queue,
            queue.c.media_download_id == MediaDownloadBase.id,
        )
        .subquery()
    )


def _recent_activity_at(status_source):
    return case(
        (
            status_source.c.status.in_(("downloaded", "redownloaded")),
            func.coalesce(
                status_source.c.run_finished_at,
                status_source.c.downloaded_at,
                status_source.c.created_at,
            ),
        ),
        else_=func.coalesce(
            status_source.c.run_finished_at,
            status_source.c.updated_at,
            status_source.c.created_at,
        ),
    ).label("recent_at")


def _workflow_bucket(status_source):
    return case(
        (status_source.c.status.in_(_ACTIVE_WORKFLOW_STATUSES), 0),
        (status_source.c.status == "pending", 1),
        else_=2,
    ).label("workflow_bucket")


def _workflow_queue_position(status_source):
    return case(
        (
            status_source.c.status == "pending",
            func.coalesce(status_source.c.queue_position, -1),
        ),
        else_=0,
    ).label("workflow_queue")


def _collection_source() -> Subquery:
    """Projection used by paging, facets and bulk actions.

    Every helper above contributes SQL expressions only. Building this relation
    performs no database I/O; SQLAlchemy folds the concepts into the statement
    executed by the caller.
    """
    status_source = _download_status_source()
    return (
        select(
            status_source,
            _recent_activity_at(status_source),
            _workflow_bucket(status_source),
            _workflow_queue_position(status_source),
        )
        .subquery()
    )


def _bulk_action_predicate(source: Subquery, action: str):
    if action == "retry":
        return source.c.status.in_(_RETRYABLE_STATUSES)
    if action == "cancel":
        return source.c.status.in_(_CANCELABLE_STATUSES)
    if action == "delete-unavailable":
        return source.c.artifact_status.in_((
            MediaDownloadArtifactStatus.ABSENT,
            MediaDownloadArtifactStatus.MISSING,
        ))
    raise ValueError(f"Unknown media download bulk action: {action}")


@dataclass(frozen=True)
class MediaDownloadCollectionQuery:
    """Composable SQL statements for the mutable media-download collection."""

    source: Subquery

    @classmethod
    def build(cls) -> "MediaDownloadCollectionQuery":
        return cls(source=_collection_source())

    def page_statement(
        self,
        *,
        statuses: Sequence[str],
        order: str,
        after=None,
        limit: int,
    ):
        predicates = []
        if statuses:
            predicates.append(self.source.c.status.in_(statuses))
        if after is not None:
            predicates.append(after)

        if order == "recent":
            ordering = (
                self.source.c.recent_at.desc(),
                self.source.c.id.desc(),
            )
        else:
            ordering = (
                self.source.c.workflow_bucket.asc(),
                self.source.c.workflow_queue.asc(),
                self.source.c.id.desc(),
            )

        return (
            select(
                self.source.c.id,
                self.source.c.queue_position,
                self.source.c.recent_at,
                self.source.c.workflow_bucket,
                self.source.c.workflow_queue,
            )
            .where(*predicates)
            .order_by(*ordering)
            .limit(limit + 1)
        )

    def facets_statement(self):
        return (
            select(self.source.c.status, func.count(self.source.c.id))
            .group_by(self.source.c.status)
        )

    def summary_statement(self, *, statuses: Sequence[str]):
        statement = select(
            func.count(self.source.c.id),
            func.coalesce(
                func.sum(case((
                    _bulk_action_predicate(self.source, "retry"),
                    1,
                ), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((
                    _bulk_action_predicate(self.source, "cancel"),
                    1,
                ), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((
                    _bulk_action_predicate(
                        self.source,
                        "delete-unavailable",
                    ),
                    1,
                ), else_=0)),
                0,
            ),
        )
        if statuses:
            statement = statement.where(self.source.c.status.in_(statuses))
        return statement

    def bulk_action_ids_statement(
        self,
        *,
        statuses: Sequence[str],
        action: str,
    ):
        predicates = [_bulk_action_predicate(self.source, action)]
        if statuses:
            predicates.append(self.source.c.status.in_(statuses))
        return (
            select(self.source.c.id)
            .where(*predicates)
            .order_by(self.source.c.id)
        )


def media_download_collection_revision(session: Session) -> str:
    """Version mutable collection state so stale cursors restart from the head."""
    download_count, download_updated = session.execute(
        select(
            func.count(MediaDownloadBase.id),
            func.max(MediaDownloadBase.updated_at),
        )
    ).one()
    operation_count, operation_updated = session.execute(
        select(
            func.count(TaskOperation.id),
            func.max(TaskOperation.updated_at),
        ).where(TaskOperation.kind == "media.download")
    ).one()
    run_count, run_updated = session.execute(
        select(
            func.count(TaskRun.id),
            func.max(TaskRun.updated_at),
        ).where(TaskRun.resource_type == ResourceType.MEDIA_DOWNLOAD)
    ).one()
    return "|".join([
        str(download_count or 0),
        download_updated.isoformat() if download_updated is not None else "",
        str(operation_count or 0),
        operation_updated.isoformat() if operation_updated is not None else "",
        str(run_count or 0),
        run_updated.isoformat() if run_updated is not None else "",
    ])
