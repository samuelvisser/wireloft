from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import (
    Session,
    joinedload,
    load_only,
    raiseload,
    selectinload,
    with_polymorphic,
)

from backend.api.pagination import (
    InvalidCursorError,
    KeysetField,
    cursor_key_values,
    decode_cursor,
    encode_cursor,
    keyset_after,
)
from backend.api.models.media_download import (
    EpisodeDownloadAPICreate,
    MediaDownloadAPIRead,
    MediaDownloadAPIReadView,
    MediaDownloadAPIUpdate,
    MediaDownloadPageRead,
    MovieDownloadAPICreate,
)
from backend.db.model_mapping import update_database_fields
from backend.db.models import (
    Episode,
    LocalMediaProfileBase,
    MediaDownloadBase,
    Movie,
    MovieExtra,
    MovieExtraSource,
    Show,
)
from backend.db.models.media_download import (
    EpisodeMediaDownload,
    MovieExtraMediaDownload,
    MovieMediaDownload,
)
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.types.episode_types import EpisodePublishStatus
from backend.types.local_media_profile_types import LocalMediaProfileType
from backend.types.media_types import MediaType
from dailywire_downloader.storage.artifacts import remove_download_artifacts
from backend.services.episode_download_delay import episode_download_delay_passed
from backend.services.media_download_history import record_media_download_history
from backend.utils.output_template import resolve_episode_output_path, resolve_movie_output_path
from dailywire_api.records import DwMovieRecord
from task_manager.scheduler.db import TaskDefinition, TaskOperation, TaskRun
from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus
from task_manager.tasks.media_download_operations import (
    get_active_media_download_operation,
    get_media_download_queue_positions,
    media_download_queue_position_subquery,
    prepare_media_download_artifact,
)
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


_DOWNLOAD_TASK_KEYS = ("download_episode", "download_movie")


def _resolve_episode_download_path(
    s: Session,
    profile,
    episode: Episode,
    download: EpisodeMediaDownload,
) -> str:
    return str(resolve_episode_output_path(
        profile.output_template,
        episode=episode,
        local_media_profile=profile,
        media_download=download,
    ))


def get_media_downloads_list(s: Session) -> list[MediaDownloadAPIRead]:
    items = s.query(MediaDownloadBase).order_by(MediaDownloadBase.id).all()
    return [MediaDownloadAPIRead.model_validate(it) for it in items]


def _latest_download_runs(s: Session, media_download_ids: list[int]) -> dict[int, TaskRun]:
    if not media_download_ids:
        return {}

    latest_ids = (
        select(
            TaskRun.resource_id.label("resource_id"),
            func.max(TaskRun.id).label("run_id"),
        )
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(
            TaskRun.resource_type == ResourceType.MEDIA_DOWNLOAD,
            TaskRun.resource_id.in_(media_download_ids),
            TaskDefinition.key.in_(_DOWNLOAD_TASK_KEYS),
        )
        .group_by(TaskRun.resource_id)
        .subquery()
    )
    rows = s.scalars(
        select(TaskRun).join(latest_ids, TaskRun.id == latest_ids.c.run_id)
    )
    return {
        int(run.resource_id): run
        for run in rows
        if run.resource_id is not None
    }


@dataclass(frozen=True)
class _MediaDownloadViewSource:
    """Typed sources consumed declaratively by MediaDownloadAPIReadView."""

    download: MediaDownloadBase
    media: Episode | Movie | MovieExtra | None
    latest_run: TaskRun | None
    queue_position: int | None

    @property
    def profile(self) -> LocalMediaProfileBase:
        return self.download.local_media_profile

    @property
    def episode(self) -> Episode | None:
        return self.media if isinstance(self.media, Episode) else None

    @property
    def movie_extra(self) -> MovieExtra | None:
        return self.media if isinstance(self.media, MovieExtra) else None

    @property
    def movie(self) -> Movie | None:
        if isinstance(self.media, Movie):
            return self.media
        if isinstance(self.media, MovieExtra):
            return self.media.movie
        return None

    @property
    def show(self) -> Show | None:
        return self.media.show if isinstance(self.media, Episode) else None

    @property
    def latest_task_is_redownload(self) -> Optional[bool]:
        return _run_is_redownload(self.latest_run)


def _run_is_redownload(run: TaskRun | None) -> Optional[bool]:
    if run is None:
        return None

    meta = run.meta if isinstance(run.meta, dict) else {}
    inputs = meta.get("inputs") if isinstance(meta.get("inputs"), dict) else {}
    value = inputs.get("is_redownload")
    if isinstance(value, bool):
        return value

    result = run.result if isinstance(run.result, dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    value = data.get("is_redownload")
    return value if isinstance(value, bool) else None


def _load_media_items_for_view(
        s: Session,
        downloads: list[MediaDownloadBase],
) -> dict[int, Episode | Movie | MovieExtra]:
    """Load the small media context required by the view in bounded ORM queries.

    Keeping this separate from the download query avoids both a wide positional
    projection and N+1s. Relationship and column raiseload guards ensure future
    view fields cannot accidentally add hidden lazy queries.
    """
    ids_by_type: dict[str, list[int]] = {}
    for download in downloads:
        ids_by_type.setdefault(download.type, []).append(download.media_item_id)

    media_by_id: dict[int, Episode | Movie | MovieExtra] = {}

    episode_ids = ids_by_type.get(MediaType.EPISODE.value, [])
    if episode_ids:
        episodes = s.scalars(
            select(Episode)
            .where(Episode.id.in_(episode_ids))
            .options(
                load_only(
                    Episode.id,
                    Episode.slug,
                    Episode.title,
                    Episode.episode_identifier,
                    raiseload=True,
                ),
                joinedload(Episode.show).load_only(
                    Show.id,
                    Show.slug,
                    Show.title,
                    raiseload=True,
                ),
                raiseload("*"),
            )
        )
        media_by_id.update((episode.id, episode) for episode in episodes)

    movie_ids = ids_by_type.get(MediaType.MOVIE.value, [])
    if movie_ids:
        movies = s.scalars(
            select(Movie)
            .where(Movie.id.in_(movie_ids))
            .options(
                load_only(
                    Movie.id,
                    Movie.slug,
                    Movie.title,
                    raiseload=True,
                ),
                raiseload("*"),
            )
        )
        media_by_id.update((movie.id, movie) for movie in movies)

    movie_extra_ids = ids_by_type.get(MediaType.MOVIE_EXTRA.value, [])
    if movie_extra_ids:
        movie_extras = s.scalars(
            select(MovieExtra)
            .where(MovieExtra.id.in_(movie_extra_ids))
            .options(
                load_only(
                    MovieExtra.id,
                    MovieExtra.movie_id,
                    MovieExtra.source_id,
                    MovieExtra.movie_extra_type,
                    raiseload=True,
                ),
                joinedload(MovieExtra.movie).load_only(
                    Movie.id,
                    Movie.slug,
                    Movie.title,
                    raiseload=True,
                ),
                joinedload(MovieExtra.source).load_only(
                    MovieExtraSource.id,
                    MovieExtraSource.slug,
                    MovieExtraSource.title,
                    raiseload=True,
                ),
                raiseload("*"),
            )
        )
        media_by_id.update((movie_extra.id, movie_extra) for movie_extra in movie_extras)

    return media_by_id


def _media_download_view_statement(
        *,
        episode_slug: Optional[str],
        movie_slug: Optional[str],
        show_slug: Optional[str],
        statuses: Optional[list[str]],
        limit: Optional[int],
        ids: Optional[list[int]] = None,
):
    """Build the scoped download query while returning complete ORM models."""
    download = with_polymorphic(MediaDownloadBase, "*")
    stmt = (
        select(download)
        .options(
            joinedload(download.local_media_profile).load_only(
                LocalMediaProfileBase.id,
                LocalMediaProfileBase.name,
                LocalMediaProfileBase.preferred_format,
                raiseload=True,
            ),
            selectinload(download.assets),
            raiseload("*"),
        )
        .order_by(download.id.desc())
    )

    if statuses:
        stmt = stmt.where(download.artifact_status.in_(statuses))

    if ids is not None:
        stmt = stmt.where(download.id.in_(ids))

    if episode_slug is not None:
        episode_ids = select(Episode.id).where(Episode.slug == episode_slug)
        stmt = stmt.where(download.media_item_id.in_(episode_ids))

    if show_slug is not None:
        show_episode_ids = (
            select(Episode.id)
            .join(Show, Show.id == Episode.show_id)
            .where(Show.slug == show_slug)
        )
        stmt = stmt.where(download.media_item_id.in_(show_episode_ids))

    if movie_slug is not None:
        movie_ids = select(Movie.id).where(Movie.slug == movie_slug)
        movie_extra_ids = select(MovieExtra.id).where(
            MovieExtra.movie_id.in_(movie_ids)
        )
        stmt = stmt.where(or_(
            download.media_item_id.in_(movie_ids),
            download.media_item_id.in_(movie_extra_ids),
        ))

    if limit is not None:
        stmt = stmt.limit(limit)

    return stmt


def _build_media_download_views(
        s: Session,
        downloads: list[MediaDownloadBase],
        *,
        latest_runs: dict[int, TaskRun] | None = None,
        queue_positions: dict[int, int] | None = None,
) -> list[MediaDownloadAPIReadView]:
    media_by_id = _load_media_items_for_view(s, downloads)
    if latest_runs is None:
        latest_runs = _latest_download_runs(s, [download.id for download in downloads])
    queue_positions = queue_positions if queue_positions is not None else get_media_download_queue_positions(s)
    return [
        MediaDownloadAPIReadView.model_validate(
            _MediaDownloadViewSource(
                download=download,
                media=media_by_id.get(download.media_item_id),
                latest_run=latest_runs.get(download.id),
                queue_position=queue_positions.get(download.id),
            )
        )
        for download in downloads
    ]


def get_media_downloads_view(
        s: Session,
        *,
        episode_slug: Optional[str] = None,
        movie_slug: Optional[str] = None,
        show_slug: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        limit: Optional[int] = None,
) -> list[MediaDownloadAPIReadView]:
    """Return scoped artifact state with all view context loaded in bounded queries."""
    downloads = list(s.scalars(_media_download_view_statement(
        episode_slug=episode_slug,
        movie_slug=movie_slug,
        show_slug=show_slug,
        statuses=statuses,
        limit=limit,
    )))
    return _build_media_download_views(s, downloads)


def _active_download_operations(
        s: Session,
        media_download_ids: list[int],
) -> dict[int, TaskOperation]:
    if not media_download_ids:
        return {}
    rows = s.scalars(
        select(TaskOperation)
        .where(
            TaskOperation.kind == "media.download",
            TaskOperation.resource_type == ResourceType.MEDIA_DOWNLOAD.value,
            TaskOperation.resource_id.in_(media_download_ids),
            TaskOperation.status.in_([
                OperationStatus.QUEUED.value,
                OperationStatus.RUNNING.value,
                OperationStatus.WAITING.value,
            ]),
        )
        .order_by(TaskOperation.created_at.desc(), TaskOperation.id.desc())
    )
    result: dict[int, TaskOperation] = {}
    for operation in rows:
        if operation.resource_id is not None:
            result.setdefault(int(operation.resource_id), operation)
    return result


def _task_status_value(run: TaskRun | None) -> str | None:
    if run is None:
        return None
    return run.status.value if isinstance(run.status, TaskStatus) else str(run.status)


def _download_collection_status(
        download: MediaDownloadBase,
        *,
        latest_run: TaskRun | None,
        active_operation: TaskOperation | None,
) -> str:
    if active_operation is not None:
        context = active_operation.context if isinstance(active_operation.context, dict) else {}
        progress_meta = latest_run.progress_metadata if latest_run is not None else None
        progress_meta = progress_meta if isinstance(progress_meta, dict) else {}
        execution = progress_meta.get("download")
        execution = execution if isinstance(execution, dict) else {}

        if (
            context.get("cancel_requested") is True
            or progress_meta.get("canceling") is True
            or execution.get("canceling") is True
        ):
            return "canceling"
        if active_operation.status == OperationStatus.QUEUED.value:
            return "pending"

        main_activity = execution.get("main_activity")
        stages = execution.get("stages")
        main_stage = next((
            stage for stage in stages
            if isinstance(stage, dict) and stage.get("id") == main_activity
        ), None) if isinstance(stages, list) else None
        wait_state = (
            main_stage.get("wait")
            if isinstance(main_stage, dict) and isinstance(main_stage.get("wait"), dict)
            else progress_meta.get("wait_state")
        )
        if isinstance(wait_state, dict) and wait_state.get("reason"):
            return "waiting"
        if active_operation.status == OperationStatus.WAITING.value:
            return "waiting"

        if execution.get("phase") == "transferring" and main_activity == "media":
            return "downloading"
        if execution.get("primary_transfer_complete") is True:
            return "local_processing"
        return "preparing"

    task_status = _task_status_value(latest_run)
    if download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
        return "redownloaded" if _run_is_redownload(latest_run) else "downloaded"
    if download.artifact_status == MediaDownloadArtifactStatus.MISSING.value:
        return "missing"
    if download.artifact_status == MediaDownloadArtifactStatus.CORRUPTED.value:
        return "corrupted"
    if task_status == TaskStatus.RUNNING.value:
        return "preparing"
    if task_status == TaskStatus.FAILED.value:
        return "error"
    if (
        download.automatic_retry_suppressed
        or task_status == TaskStatus.CANCELED.value
    ):
        return "cancelled"
    return "not_downloaded"


def _download_bulk_action_matches(
        download: MediaDownloadBase,
        status: str,
        action: str,
) -> bool:
    if action == "retry":
        return status in {
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
        }
    if action == "cancel":
        return status in {
            "pending",
            "preparing",
            "waiting",
            "downloading",
            "local_processing",
        }
    if action == "delete-unavailable":
        return download.artifact_status in {
            MediaDownloadArtifactStatus.ABSENT.value,
            MediaDownloadArtifactStatus.MISSING.value,
        }
    raise ValueError(f"Unknown media download bulk action: {action}")


def _latest_download_run_ids_subquery():
    return (
        select(
            TaskRun.resource_id.label("media_download_id"),
            func.max(TaskRun.id).label("run_id"),
        )
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(
            TaskRun.resource_type == ResourceType.MEDIA_DOWNLOAD,
            TaskDefinition.key.in_(_DOWNLOAD_TASK_KEYS),
        )
        .group_by(TaskRun.resource_id)
        .subquery()
    )


def _latest_active_download_operation_subquery():
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
            TaskOperation.status.in_((
                OperationStatus.QUEUED.value,
                OperationStatus.RUNNING.value,
                OperationStatus.WAITING.value,
            )),
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


def _media_download_collection_source():
    """Build the UI download status/order projection entirely in SQL."""
    latest_run_ids = _latest_download_run_ids_subquery()
    active_operation = _latest_active_download_operation_subquery()
    queue = media_download_queue_position_subquery()

    progress_meta = TaskRun.meta["_progress_meta"]
    execution = progress_meta["download"]
    stages = func.json_each(
        TaskRun.meta,
        '$."_progress_meta".download.stages',
    ).table_valued("key", "value").alias("download_stage")
    main_stage_wait = exists(
        select(stages.c.key)
        .where(
            func.json_extract(stages.c.value, "$.id")
            == execution["main_activity"].as_string(),
            func.json_extract(stages.c.value, "$.wait.reason").is_not(None),
        )
    )
    canceling = or_(
        func.coalesce(
            active_operation.c.operation_context["cancel_requested"].as_boolean(),
            False,
        ).is_(True),
        func.coalesce(progress_meta["canceling"].as_boolean(), False).is_(True),
        func.coalesce(execution["canceling"].as_boolean(), False).is_(True),
    )
    waiting = or_(
        active_operation.c.operation_status == OperationStatus.WAITING.value,
        main_stage_wait,
        progress_meta["wait_state"]["reason"].as_string().is_not(None),
    )
    transferring = and_(
        execution["phase"].as_string() == "transferring",
        execution["main_activity"].as_string() == "media",
    )
    primary_transfer_complete = func.coalesce(
        execution["primary_transfer_complete"].as_boolean(),
        False,
    ).is_(True)
    is_redownload = func.coalesce(
        TaskRun.meta["inputs"]["is_redownload"].as_boolean(),
        TaskRun.result["data"]["is_redownload"].as_boolean(),
        False,
    )

    active_status = case(
        (canceling, "canceling"),
        (
            active_operation.c.operation_status == OperationStatus.QUEUED.value,
            "pending",
        ),
        (waiting, "waiting"),
        (transferring, "downloading"),
        (primary_transfer_complete, "local_processing"),
        else_="preparing",
    )
    persistent_status = case(
        (
            MediaDownloadBase.artifact_status
            == MediaDownloadArtifactStatus.AVAILABLE.value,
            case((is_redownload.is_(True), "redownloaded"), else_="downloaded"),
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
    status = case(
        (active_operation.c.operation_id.is_not(None), active_status),
        else_=persistent_status,
    ).label("status")

    status_source = (
        select(
            MediaDownloadBase.id.label("id"),
            MediaDownloadBase.artifact_status.label("artifact_status"),
            MediaDownloadBase.downloaded_at.label("downloaded_at"),
            MediaDownloadBase.created_at.label("created_at"),
            MediaDownloadBase.updated_at.label("updated_at"),
            TaskRun.finished_at.label("run_finished_at"),
            queue.c.queue_position.label("queue_position"),
            status,
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

    recent_at = case(
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
    workflow_bucket = case(
        (
            status_source.c.status.in_((
                "downloading",
                "preparing",
                "waiting",
                "canceling",
                "local_processing",
            )),
            0,
        ),
        (status_source.c.status == "pending", 1),
        else_=2,
    ).label("workflow_bucket")
    workflow_queue = case(
        (
            status_source.c.status == "pending",
            func.coalesce(status_source.c.queue_position, -1),
        ),
        else_=0,
    ).label("workflow_queue")

    return (
        select(
            status_source,
            recent_at,
            workflow_bucket,
            workflow_queue,
        )
        .subquery()
    )


def _download_bulk_action_predicate(source, action: str):
    if action == "retry":
        return source.c.status.in_((
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
        ))
    if action == "cancel":
        return source.c.status.in_((
            "pending",
            "preparing",
            "waiting",
            "downloading",
            "local_processing",
        ))
    if action == "delete-unavailable":
        return source.c.artifact_status.in_((
            MediaDownloadArtifactStatus.ABSENT.value,
            MediaDownloadArtifactStatus.MISSING.value,
        ))
    raise ValueError(f"Unknown media download bulk action: {action}")


def _download_collection_revision(s: Session) -> str:
    download_count, download_updated = s.execute(
        select(func.count(MediaDownloadBase.id), func.max(MediaDownloadBase.updated_at))
    ).one()
    operation_count, operation_updated = s.execute(
        select(func.count(TaskOperation.id), func.max(TaskOperation.updated_at)).where(
            TaskOperation.kind == "media.download",
        )
    ).one()
    run_count, run_updated = s.execute(
        select(func.count(TaskRun.id), func.max(TaskRun.updated_at)).where(
            TaskRun.resource_type == ResourceType.MEDIA_DOWNLOAD,
        )
    ).one()
    return "|".join([
        str(download_count or 0),
        download_updated.isoformat() if download_updated is not None else "",
        str(operation_count or 0),
        operation_updated.isoformat() if operation_updated is not None else "",
        str(run_count or 0),
        run_updated.isoformat() if run_updated is not None else "",
    ])


def get_media_downloads_page(
        s: Session,
        *,
        statuses: Optional[list[str]] = None,
        order: str = "workflow",
        cursor: str | None = None,
        limit: int = 50,
) -> MediaDownloadPageRead:
    """Return one SQL-filtered cursor page in the requested UI ordering."""
    source = _media_download_collection_source()
    requested_statuses = sorted(set(statuses or []))
    revision = _download_collection_revision(s)

    page_filter = []
    if requested_statuses:
        page_filter.append(source.c.status.in_(requested_statuses))

    cursor_values: list[str | int | float | None] | None = None
    if cursor:
        try:
            values = decode_cursor(cursor)
            if (
                values.get("kind") != "media-download"
                or values.get("order") != order
                or values.get("statuses") != requested_statuses
            ):
                raise InvalidCursorError(
                    "Cursor does not match this download collection"
                )
            if values.get("revision") == revision:
                cursor_values = cursor_key_values(
                    values,
                    length=2 if order == "recent" else 3,
                )
        except InvalidCursorError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if order == "recent":
        order_by = (source.c.recent_at.desc(), source.c.id.desc())
        if cursor_values is not None:
            occurred_at, media_download_id = cursor_values
            if (
                not isinstance(occurred_at, str)
                or isinstance(media_download_id, bool)
                or not isinstance(media_download_id, int)
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Invalid download cursor key",
                )
            try:
                parsed_occurred_at = datetime.fromisoformat(occurred_at)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid download cursor key",
                ) from exc
            page_filter.append(keyset_after([
                KeysetField(
                    source.c.recent_at,
                    parsed_occurred_at,
                    descending=True,
                ),
                KeysetField(
                    source.c.id,
                    media_download_id,
                    descending=True,
                ),
            ]))
    else:
        order_by = (
            source.c.workflow_bucket.asc(),
            source.c.workflow_queue.asc(),
            source.c.id.desc(),
        )
        if cursor_values is not None:
            if (
                any(isinstance(value, bool) for value in cursor_values)
                or not all(isinstance(value, int) for value in cursor_values)
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Invalid download cursor key",
                )
            bucket, queue_position, media_download_id = cursor_values
            page_filter.append(keyset_after([
                KeysetField(source.c.workflow_bucket, bucket),
                KeysetField(source.c.workflow_queue, queue_position),
                KeysetField(
                    source.c.id,
                    media_download_id,
                    descending=True,
                ),
            ]))

    page_stmt = (
        select(
            source.c.id,
            source.c.queue_position,
            source.c.recent_at,
            source.c.workflow_bucket,
            source.c.workflow_queue,
        )
        .where(*page_filter)
        .order_by(*order_by)
        .limit(limit + 1)
    )
    page_rows = list(s.execute(page_stmt).mappings())
    has_more = len(page_rows) > limit
    page_rows = page_rows[:limit]
    selected_ids = [int(row["id"]) for row in page_rows]

    facet_rows = s.execute(
        select(source.c.status, func.count(source.c.id))
        .group_by(source.c.status)
    )
    status_counts = {
        str(status): int(count)
        for status, count in facet_rows
    }

    summary_stmt = select(
        func.count(source.c.id),
        func.coalesce(
            func.sum(case((
                _download_bulk_action_predicate(source, "retry"),
                1,
            ), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(case((
                _download_bulk_action_predicate(source, "cancel"),
                1,
            ), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(case((
                _download_bulk_action_predicate(source, "delete-unavailable"),
                1,
            ), else_=0)),
            0,
        ),
    )
    if requested_statuses:
        summary_stmt = summary_stmt.where(
            source.c.status.in_(requested_statuses),
        )
    total, retry_count, cancel_count, delete_count = s.execute(
        summary_stmt
    ).one()
    action_counts = {
        "retry": int(retry_count),
        "cancel": int(cancel_count),
        "delete-unavailable": int(delete_count),
    }

    if selected_ids:
        selected_downloads_by_id = {
            download.id: download
            for download in s.scalars(
                _media_download_view_statement(
                    episode_slug=None,
                    movie_slug=None,
                    show_slug=None,
                    statuses=None,
                    limit=None,
                    ids=selected_ids,
                )
            )
        }
        selected_downloads = [
            selected_downloads_by_id[media_download_id]
            for media_download_id in selected_ids
            if media_download_id in selected_downloads_by_id
        ]
        latest_runs = _latest_download_runs(s, selected_ids)
        queue_positions = {
            int(row["id"]): int(row["queue_position"])
            for row in page_rows
            if row["queue_position"] is not None
        }
    else:
        selected_downloads = []
        latest_runs = {}
        queue_positions = {}

    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        if order == "recent":
            recent_at = last["recent_at"]
            if recent_at is None:
                raise RuntimeError("Download recent ordering produced no timestamp")
            cursor_key = [recent_at.isoformat(), int(last["id"])]
        else:
            cursor_key = [
                int(last["workflow_bucket"]),
                int(last["workflow_queue"]),
                int(last["id"]),
            ]
        next_cursor = encode_cursor({
            "kind": "media-download",
            "order": order,
            "statuses": requested_statuses,
            "revision": revision,
            "key": cursor_key,
        })

    return MediaDownloadPageRead(
        items=_build_media_download_views(
            s,
            selected_downloads,
            latest_runs=latest_runs,
            queue_positions=queue_positions,
        ),
        total=int(total),
        limit=limit,
        next_cursor=next_cursor,
        revision=revision,
        facets=status_counts,
        actions=action_counts,
    )


def get_media_download_bulk_action_ids(
        s: Session,
        *,
        statuses: Optional[list[str]],
        action: str,
) -> list[int]:
    """Return exact bulk-action IDs using the same SQL status projection as paging."""
    source = _media_download_collection_source()
    predicates = [_download_bulk_action_predicate(source, action)]
    requested_statuses = sorted(set(statuses or []))
    if requested_statuses:
        predicates.append(source.c.status.in_(requested_statuses))

    return [
        int(media_download_id)
        for media_download_id in s.scalars(
            select(source.c.id)
            .where(*predicates)
            .order_by(source.c.id)
        )
    ]


def get_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = s.query(MediaDownloadBase).filter_by(id=media_download_id).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    return MediaDownloadAPIRead.model_validate(item)


def _assert_no_active_attempt(s: Session, download: MediaDownloadBase) -> None:
    if get_active_media_download_operation(s, download.id) is not None:
        raise HTTPException(status_code=409, detail="This download already has an active operation")


def _reconcile_existing_artifact(s: Session, download: MediaDownloadBase) -> None:
    if download.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
        resolve_media_download_file(s, download)


def create_episode_download(s: Session, episode_slug: str, body: EpisodeDownloadAPICreate) -> EpisodeMediaDownload:
    episode: Optional[Episode] = s.query(Episode).filter(Episode.slug == episode_slug).one_or_none()
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value:
        raise HTTPException(status_code=422, detail="Episode has no usable media")
    if episode.publish_status == EpisodePublishStatus.DW_PROCESSING.value:
        raise HTTPException(status_code=422, detail="Episode media is still processing on Daily Wire")

    profile = _get_profile(s, body.local_media_profile_id, LocalMediaProfileType.SHOW)
    redownload_when_final = (
        body.redownload_when_final
        and episode.publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value
    )
    redownload_when_delay_passed = (
        body.redownload_when_delay_passed
        and not body.schedule_for_delay
        and episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL
        and not episode_download_delay_passed(episode)
    )
    existing: Optional[EpisodeMediaDownload] = (
        s.query(EpisodeMediaDownload)
        .filter(
            EpisodeMediaDownload.media_item_id == episode.id,
            EpisodeMediaDownload.local_media_profile_id == profile.id,
        )
        .one_or_none()
    )
    if existing is not None:
        _assert_no_active_attempt(s, existing)
        existing.redownload_when_final = redownload_when_final
        existing.redownload_when_delay_passed = redownload_when_delay_passed
        _reconcile_existing_artifact(s, existing)
        if existing.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
            raise HTTPException(status_code=409, detail=f"Episode already has a downloaded file for profile '{profile.name}'")
        prepare_media_download_artifact(s, existing)
        existing.file_path = _resolve_episode_download_path(s, profile, episode, existing)
        s.flush()
        return existing

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        file_path="",
        redownload_when_final=redownload_when_final,
        redownload_when_delay_passed=redownload_when_delay_passed,
    )
    s.add(download)
    s.flush()
    download.file_path = _resolve_episode_download_path(s, profile, episode, download)
    s.flush()
    record_media_download_history(
        s,
        download.id,
        MediaDownloadHistoryAction.CREATED,
        metadata={
            "file_path": download.file_path,
            "local_media_profile_id": profile.id,
        },
    )
    return download


def create_movie_download(
    s: Session,
    movie_data: DwMovieRecord,
    body: MovieDownloadAPICreate,
) -> MovieMediaDownload:
    profile = _get_profile(s, body.local_media_profile_id, LocalMediaProfileType.MOVIE)
    if not movie_data.is_downloadable:
        raise HTTPException(status_code=422, detail="Daily Wire marks this movie as unavailable for download")

    movie = _get_or_create_movie(s, movie_data)
    existing: Optional[MovieMediaDownload] = (
        s.query(MovieMediaDownload)
        .filter(
            MovieMediaDownload.media_item_id == movie.id,
            MovieMediaDownload.local_media_profile_id == profile.id,
        )
        .one_or_none()
    )
    if existing is not None:
        _assert_no_active_attempt(s, existing)
        _reconcile_existing_artifact(s, existing)
        if existing.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
            raise HTTPException(status_code=409, detail=f"Movie already has a downloaded file for profile '{profile.name}'")
        prepare_media_download_artifact(s, existing)
        existing.file_path = str(resolve_movie_output_path(profile.output_template, movie=movie))
        s.flush()
        return existing

    download = MovieMediaDownload(
        type=MediaType.MOVIE.value,
        media_item_id=movie.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        file_path=str(resolve_movie_output_path(profile.output_template, movie=movie)),
    )
    s.add(download)
    s.flush()
    record_media_download_history(
        s,
        download.id,
        MediaDownloadHistoryAction.CREATED,
        metadata={
            "file_path": download.file_path,
            "local_media_profile_id": profile.id,
        },
    )
    return download


def create_movie_extra_download(
    s: Session,
    movie_data: DwMovieRecord,
    movie_extra_slug: str,
    body: MovieDownloadAPICreate,
) -> MovieExtraMediaDownload:
    """Persist a browsed movie extra and queue it with a Movie profile."""
    profile = _get_profile(s, body.local_media_profile_id, LocalMediaProfileType.MOVIE)
    remote_extra = next((extra for extra in movie_data.movie_extras if extra.slug == movie_extra_slug), None)
    if remote_extra is None:
        raise HTTPException(status_code=404, detail="Movie extra not found for this movie")

    movie = _get_or_create_movie(s, movie_data)
    movie_extra: Optional[MovieExtra] = (
        s.query(MovieExtra)
        .filter(MovieExtra.movie_id == movie.id, MovieExtra.slug == movie_extra_slug)
        .one_or_none()
    )
    if movie_extra is None:
        raise HTTPException(status_code=404, detail="Movie extra could not be persisted for this movie")

    existing: Optional[MovieExtraMediaDownload] = (
        s.query(MovieExtraMediaDownload)
        .filter(
            MovieExtraMediaDownload.media_item_id == movie_extra.id,
            MovieExtraMediaDownload.local_media_profile_id == profile.id,
        )
        .one_or_none()
    )
    if existing is not None:
        _assert_no_active_attempt(s, existing)
        _reconcile_existing_artifact(s, existing)
        if existing.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value:
            raise HTTPException(status_code=409, detail=f"Movie extra already has a downloaded file for profile '{profile.name}'")
        prepare_media_download_artifact(s, existing)
        existing.file_path = str(resolve_movie_output_path(profile.output_template, movie=movie, media_item=movie_extra))
        s.flush()
        return existing

    download = MovieExtraMediaDownload(
        type=MediaType.MOVIE_EXTRA.value,
        media_item_id=movie_extra.id,
        local_media_profile_id=profile.id,
        artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
        file_path=str(resolve_movie_output_path(profile.output_template, movie=movie, media_item=movie_extra)),
    )
    s.add(download)
    s.flush()
    record_media_download_history(
        s,
        download.id,
        MediaDownloadHistoryAction.CREATED,
        metadata={
            "file_path": download.file_path,
            "local_media_profile_id": profile.id,
        },
    )
    return download


def _get_profile(s: Session, profile_id: int, expected_type: LocalMediaProfileType) -> LocalMediaProfileBase:
    profile: Optional[LocalMediaProfileBase] = s.get(LocalMediaProfileBase, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Local media profile not found")
    if profile.type != expected_type.value:
        label = "Movies and movie extras" if expected_type == LocalMediaProfileType.MOVIE else "Episodes"
        raise HTTPException(status_code=422, detail=f"{label} require a {expected_type.value.title()} Local Media Profile")
    return profile


def _get_or_create_movie(s: Session, movie_data: DwMovieRecord) -> Movie:
    from backend.services.movies import index_dailywire_movie
    movie, _ = index_dailywire_movie(s, movie_data)
    return movie


def retry_media_download(s: Session, media_download_id: int) -> MediaDownloadBase:
    download: Optional[MediaDownloadBase] = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    _assert_no_active_attempt(s, download)
    _reconcile_existing_artifact(s, download)
    prepare_media_download_artifact(s, download)
    s.flush()
    return download


def suppress_media_download_automatic_retry(s: Session, media_download_id: int) -> MediaDownloadBase:
    """Persist the user's choice not to have a Download Profile immediately re-arm this artifact."""
    download: Optional[MediaDownloadBase] = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    download.automatic_retry_suppressed = True
    if download.artifact_status == MediaDownloadArtifactStatus.ABSENT.value:
        remove_download_artifacts(download.file_path, sidecar_paths=tuple(asset.path for asset in download.assets))
    s.flush()
    return download


def update_media_download(s: Session, media_download_id: int, body: MediaDownloadAPIUpdate) -> MediaDownloadAPIRead:
    item: Optional[MediaDownloadBase] = s.query(MediaDownloadBase).filter_by(id=media_download_id).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    update_database_fields(item, body)
    s.flush()
    return MediaDownloadAPIRead.model_validate(item)
