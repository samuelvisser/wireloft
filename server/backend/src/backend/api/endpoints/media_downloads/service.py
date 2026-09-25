from __future__ import annotations

from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.model_mapping import update_database_fields
from backend.api.models.media_download import *
from backend.db.models import Episode, LocalMediaProfileBase, Movie, MovieExtra
from backend.db.models.media_download import (
    EpisodeMediaDownload,
    MediaDownloadBase,
    MovieExtraMediaDownload,
    MovieMediaDownload,
)
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.episode_types import EpisodePublishStatus
from backend.types.local_media_profile_types import LocalMediaProfileType
from backend.types.media_types import MediaType
from task_manager.tasks.helpers.downloads.download_files import remove_download_artifacts
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
class _MediaDownloadViewSource:
    download: MediaDownloadBase
    profile: LocalMediaProfileBase
    latest_run: TaskRun | None
    queue_position: int | None

    @property
    def media(self):
        return self.download.media

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
        return self.movie_extra.movie if self.movie_extra is not None else None

    @property
    def show(self):
        return self.episode.show if self.episode is not None else None

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
        statuses: Optional[list[str]] = None,
        limit: Optional[int] = None,
) -> list[MediaDownloadAPIReadView]:
    """Return persistent media-artifact state plus latest canonical TaskRun facts."""
    stmt = (
        select(MediaDownloadBase, LocalMediaProfileBase)
        .join(
            LocalMediaProfileBase,
            LocalMediaProfileBase.id == MediaDownloadBase.local_media_profile_id,
        )
        .order_by(MediaDownloadBase.id.desc())
    )
    if statuses:
        stmt = stmt.where(MediaDownloadBase.artifact_status.in_(statuses))

    rows = list(s.execute(stmt))
    latest_runs = _latest_download_runs(s, [download.id for download, _ in rows])
    queue_positions = get_media_download_queue_positions(s)

    views: list[MediaDownloadAPIReadView] = []
    for download, profile in rows:
        source = _MediaDownloadViewSource(
            download=download,
            profile=profile,
            latest_run=latest_runs.get(download.id),
            queue_position=queue_positions.get(download.id),
        )
        if episode_slug is not None and (
            source.episode is None or source.episode.slug != episode_slug
        ):
            continue
        if movie_slug is not None and (
            source.movie is None or source.movie.slug != movie_slug
        ):
            continue

        views.append(MediaDownloadAPIReadView.model_validate(source))
        if limit is not None and len(views) >= limit:
            break
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
        remove_download_artifacts(download.file_path, download.thumbnail_path)
    s.flush()
    return download


def update_media_download(s: Session, media_download_id: int, body: MediaDownloadAPIUpdate) -> MediaDownloadAPIRead:
    item: Optional[MediaDownloadBase] = s.query(MediaDownloadBase).filter_by(id=media_download_id).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    update_database_fields(item, body)
    s.flush()
    return MediaDownloadAPIRead.model_validate(item)


def delete_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = s.query(MediaDownloadBase).filter_by(id=media_download_id).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    if item.first_successful_download_at is not None:
        raise HTTPException(
            status_code=409,
            detail="A MediaDownload that has successfully downloaded a file is permanent history and cannot be deleted",
        )
    _assert_no_active_attempt(s, item)

    resolved_path = None
    if item.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
        resolved_path = resolve_media_download_file(s, item)

    payload = MediaDownloadAPIRead.model_validate(item)
    remove_download_artifacts(
        str(resolved_path) if resolved_path is not None else item.file_path,
        item.thumbnail_path,
    )
    s.delete(item)
    s.flush()
    return payload
