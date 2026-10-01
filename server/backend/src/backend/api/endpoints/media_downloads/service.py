from __future__ import annotations

from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.db.model_mapping import update_database_fields
from backend.api.models.media_download import *
from backend.db.models import Episode, LocalMediaProfileBase, Movie, MovieExtra, MovieExtraSource, Show
from backend.db.models.media_download import (
    EpisodeMediaDownload,
    MediaDownloadBase,
    MovieExtraMediaDownload,
    MovieMediaDownload,
)
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.types.episode_types import EpisodePublishStatus
from backend.types.local_media_profile_types import LocalMediaProfileType
from backend.types.media_types import MediaType
from dailywire_downloader.storage.artifacts import remove_download_artifacts
from backend.services.media_download_history import record_media_download_history
from backend.utils.output_template import resolve_episode_output_path, resolve_movie_output_path
from dailywire_api.records import DwMovieRecord
from task_manager.scheduler.db import TaskDefinition, TaskRun
from task_manager.scheduler.types import ResourceType
from task_manager.tasks.media_download_operations import (
    get_active_media_download_operation,
    get_media_download_queue_positions,
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

    rows = s.scalars(
        select(TaskRun)
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(
            TaskRun.resource_type == ResourceType.MEDIA_DOWNLOAD,
            TaskRun.resource_id.in_(media_download_ids),
            TaskDefinition.key.in_(_DOWNLOAD_TASK_KEYS),
        )
        .order_by(TaskRun.id.desc())
    )
    latest: dict[int, TaskRun] = {}
    for run in rows:
        if run.resource_id is not None:
            latest.setdefault(run.resource_id, run)
    return latest


@dataclass(frozen=True)
class _MediaContext:
    slug: str
    title: str


@dataclass(frozen=True)
class _EpisodeContext(_MediaContext):
    episode_identifier: str


@dataclass(frozen=True)
class _ShowContext:
    slug: str
    title: str


@dataclass(frozen=True)
class _MovieExtraContext:
    movie_extra_type: str


@dataclass(frozen=True)
class _MediaDownloadViewSource:
    download: MediaDownloadBase
    profile: LocalMediaProfileBase
    latest_run: TaskRun | None
    queue_position: int | None
    media: _MediaContext | None
    episode: _EpisodeContext | None
    show: _ShowContext | None
    movie: _MediaContext | None
    movie_extra: _MovieExtraContext | None
    downloaded_publish_status: str | None

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


def get_media_downloads_view(
        s: Session,
        *,
        episode_slug: Optional[str] = None,
        movie_slug: Optional[str] = None,
        show_slug: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        limit: Optional[int] = None,
) -> list[MediaDownloadAPIReadView]:
    """Return persistent artifact state without lazy-loading media context per row."""
    episode_table = Episode.__table__
    movie_table = Movie.__table__
    movie_extra_table = MovieExtra.__table__
    movie_extra_source_table = MovieExtraSource.__table__
    show_table = Show.__table__
    episode_download_table = EpisodeMediaDownload.__table__
    parent_movie = movie_table.alias("media_download_parent_movie")

    stmt = (
        select(
            MediaDownloadBase,
            LocalMediaProfileBase,
            episode_table.c.slug.label("episode_slug"),
            episode_table.c.title.label("episode_title"),
            episode_table.c.episode_identifier.label("episode_identifier"),
            show_table.c.slug.label("show_slug"),
            show_table.c.title.label("show_title"),
            movie_table.c.slug.label("direct_movie_slug"),
            movie_table.c.title.label("direct_movie_title"),
            movie_extra_source_table.c.slug.label("movie_extra_slug"),
            movie_extra_source_table.c.title.label("movie_extra_title"),
            movie_extra_table.c.movie_extra_type.label("movie_extra_type"),
            parent_movie.c.slug.label("parent_movie_slug"),
            parent_movie.c.title.label("parent_movie_title"),
            episode_download_table.c.downloaded_publish_status.label("downloaded_publish_status"),
        )
        .join(
            LocalMediaProfileBase,
            LocalMediaProfileBase.id == MediaDownloadBase.local_media_profile_id,
        )
        .outerjoin(
            episode_table,
            episode_table.c.id == MediaDownloadBase.media_item_id,
        )
        .outerjoin(
            show_table,
            show_table.c.id == episode_table.c.show_id,
        )
        .outerjoin(
            movie_table,
            movie_table.c.id == MediaDownloadBase.media_item_id,
        )
        .outerjoin(
            movie_extra_table,
            movie_extra_table.c.id == MediaDownloadBase.media_item_id,
        )
        .outerjoin(
            movie_extra_source_table,
            movie_extra_source_table.c.id == movie_extra_table.c.source_id,
        )
        .outerjoin(
            parent_movie,
            parent_movie.c.id == movie_extra_table.c.movie_id,
        )
        .outerjoin(
            episode_download_table,
            episode_download_table.c.id == MediaDownloadBase.id,
        )
        .options(selectinload(MediaDownloadBase.assets))
        .order_by(MediaDownloadBase.id.desc())
    )

    if statuses:
        stmt = stmt.where(MediaDownloadBase.artifact_status.in_(statuses))
    if episode_slug is not None:
        stmt = stmt.where(episode_table.c.slug == episode_slug)
    if show_slug is not None:
        stmt = stmt.where(show_table.c.slug == show_slug)
    if movie_slug is not None:
        stmt = stmt.where(or_(
            movie_table.c.slug == movie_slug,
            parent_movie.c.slug == movie_slug,
        ))
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = list(s.execute(stmt))
    download_ids = [row[0].id for row in rows]
    latest_runs = _latest_download_runs(s, download_ids)
    queue_positions = get_media_download_queue_positions(s)

    views: list[MediaDownloadAPIReadView] = []
    for row in rows:
        (
            download,
            profile,
            episode_slug_value,
            episode_title,
            episode_identifier,
            show_slug_value,
            show_title,
            direct_movie_slug,
            direct_movie_title,
            movie_extra_slug,
            movie_extra_title,
            movie_extra_type,
            parent_movie_slug,
            parent_movie_title,
            downloaded_publish_status,
        ) = row

        episode = (
            _EpisodeContext(
                slug=episode_slug_value,
                title=episode_title,
                episode_identifier=episode_identifier,
            )
            if episode_slug_value is not None
            else None
        )
        show = (
            _ShowContext(slug=show_slug_value, title=show_title)
            if show_slug_value is not None
            else None
        )

        resolved_movie_slug = direct_movie_slug or parent_movie_slug
        resolved_movie_title = direct_movie_title or parent_movie_title
        movie = (
            _MediaContext(slug=resolved_movie_slug, title=resolved_movie_title)
            if resolved_movie_slug is not None
            else None
        )
        movie_extra = (
            _MovieExtraContext(movie_extra_type=movie_extra_type)
            if movie_extra_slug is not None and movie_extra_type is not None
            else None
        )
        media = episode or (
            _MediaContext(slug=movie_extra_slug, title=movie_extra_title)
            if movie_extra_slug is not None
            else movie
        )

        source = _MediaDownloadViewSource(
            download=download,
            profile=profile,
            latest_run=latest_runs.get(download.id),
            queue_position=queue_positions.get(download.id),
            media=media,
            episode=episode,
            show=show,
            movie=movie,
            movie_extra=movie_extra,
            downloaded_publish_status=downloaded_publish_status,
        )
        views.append(MediaDownloadAPIReadView.model_validate(source))

    return views

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
