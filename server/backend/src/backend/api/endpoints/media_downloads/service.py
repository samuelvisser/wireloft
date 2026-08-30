from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.media_download import *
from backend.api.models.movie import MovieAPICreate
from backend.api.models.trailer import TrailerAPICreate
from backend.db.models import Episode, LocalMediaProfileBase, Movie, Show, Trailer
from backend.db.models.media_download import (
    EpisodeMediaDownload,
    MediaDownloadAttempt,
    MediaDownloadBase,
    MovieMediaDownload,
    TrailerMediaDownload,
)
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import LocalMediaProfileType
from backend.types.media_types import MediaType
from backend.utils.download_files import remove_download_artifacts
from backend.utils.output_template import resolve_episode_output_path, resolve_movie_output_path
from dailywire_api.records import DwMovieRecord

_RESTARTABLE_STATUSES = {
    MediaDownloadStatus.PENDING.value,
    MediaDownloadStatus.CANCELLED.value,
    MediaDownloadStatus.ERROR.value,
    MediaDownloadStatus.MISSING.value,
    MediaDownloadStatus.CORRUPTED.value,
}
_ACTIVE_STATUSES = {
    MediaDownloadStatus.DOWNLOADING.value,
    MediaDownloadStatus.LOCAL_PROCESSING.value,
}
_RETRYABLE_STATUSES = _RESTARTABLE_STATUSES | _ACTIVE_STATUSES
_CANCELLABLE_STATUSES = _ACTIVE_STATUSES | {MediaDownloadStatus.PENDING.value}
_USER_CANCEL_MESSAGE = "Cancelled by the user"
_USER_RESTART_MESSAGE = "Cancelled by the user and restarted"


def get_media_downloads_list(s: Session) -> list[MediaDownloadAPIRead]:
    items = s.query(MediaDownloadBase).order_by(MediaDownloadBase.id).all()
    return [MediaDownloadAPIRead.model_validate(it) for it in items]


def get_media_downloads_view(
        s: Session,
        *,
        episode_slug: Optional[str] = None,
        movie_slug: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        limit: Optional[int] = None,
) -> list[MediaDownloadAPIReadView]:
    """Downloads joined with media and profile context, newest first."""
    stmt = (
        select(MediaDownloadBase, LocalMediaProfileBase)
        .join(LocalMediaProfileBase, LocalMediaProfileBase.id == MediaDownloadBase.local_media_profile_id)
        .order_by(MediaDownloadBase.id.desc())
    )
    if statuses:
        stmt = stmt.where(MediaDownloadBase.download_status.in_(statuses))

    views: list[MediaDownloadAPIReadView] = []
    for download, profile in s.execute(stmt):
        media = download.media
        episode = media if isinstance(media, Episode) else None
        trailer = media if isinstance(media, Trailer) else None
        movie = media if isinstance(media, Movie) else (trailer.movie if trailer else None)
        if episode_slug is not None and (episode is None or episode.slug != episode_slug):
            continue
        if movie_slug is not None and (movie is None or movie.slug != movie_slug):
            continue
        show = episode.show if episode else None
        base = MediaDownloadAPIRead.model_validate(download)
        views.append(MediaDownloadAPIReadView(
            **base.model_dump(by_alias=False),
            media_slug=getattr(media, "slug", None),
            media_title=getattr(media, "title", None),
            episode_slug=episode.slug if episode else None,
            episode_title=episode.title if episode else None,
            episode_identifier=episode.episode_identifier if episode else None,
            show_slug=show.slug if show else None,
            show_title=show.title if show else None,
            movie_slug=movie.slug if movie else None,
            movie_title=movie.title if movie else None,
            local_media_profile_name=profile.name,
            preferred_format=profile.preferred_format,
            is_redownload_attempt=getattr(download, "is_redownload_attempt", None),
            downloaded_publish_status=getattr(download, "downloaded_publish_status", None),
        ))
        if limit is not None and len(views) >= limit:
            break
    return views


def get_media_download_attempts(s: Session, media_download_id: int) -> list[MediaDownloadAttemptAPIRead]:
    if s.get(MediaDownloadBase, media_download_id) is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    items = (
        s.query(MediaDownloadAttempt)
        .filter_by(media_download_id=media_download_id)
        .order_by(MediaDownloadAttempt.id.desc())
        .all()
    )
    return [MediaDownloadAttemptAPIRead.model_validate(it) for it in items]


def get_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = s.query(MediaDownloadBase).filter_by(id=media_download_id).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    return MediaDownloadAPIRead.model_validate(item)


def create_episode_download(s: Session, episode_slug: str, body: EpisodeDownloadAPICreate) -> EpisodeMediaDownload:
    episode: Optional[Episode] = s.query(Episode).filter(Episode.slug == episode_slug).one_or_none()
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if episode.is_no_show_today:
        raise HTTPException(status_code=422, detail="This is not a downloadable episode")

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
        if existing.download_status not in _RESTARTABLE_STATUSES:
            raise HTTPException(status_code=409, detail=f"Episode already has a download for profile '{profile.name}'")
        _reset_download(existing)
        s.flush()
        return existing

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        download_status=MediaDownloadStatus.PENDING.value,
        file_path=str(resolve_episode_output_path(profile.output_template, episode=episode)),
        progress=0,
    )
    s.add(download)
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
        if existing.download_status not in _RESTARTABLE_STATUSES:
            raise HTTPException(status_code=409, detail=f"Movie already has a download for profile '{profile.name}'")
        _reset_download(existing)
        s.flush()
        return existing

    download = MovieMediaDownload(
        type=MediaType.MOVIE.value,
        media_item_id=movie.id,
        local_media_profile_id=profile.id,
        download_status=MediaDownloadStatus.PENDING.value,
        file_path=str(resolve_movie_output_path(
            profile.output_template,
            movie=movie,
            append_media_type_to_filename=profile.append_media_type_to_filename,
        )),
        progress=0,
    )
    s.add(download)
    s.flush()
    return download


def create_trailer_download(
    s: Session,
    movie_data: DwMovieRecord,
    trailer_slug: str,
    body: MovieDownloadAPICreate,
) -> TrailerMediaDownload:
    """Persist a browsed movie/trailer and queue the trailer with a Movie profile."""
    profile = _get_profile(s, body.local_media_profile_id, LocalMediaProfileType.MOVIE)
    if movie_data.trailer is None or movie_data.trailer.slug != trailer_slug:
        raise HTTPException(status_code=404, detail="Trailer not found for this movie")

    movie = _get_or_create_movie(s, movie_data)
    trailer: Optional[Trailer] = (
        s.query(Trailer)
        .filter(Trailer.movie_id == movie.id, Trailer.slug == trailer_slug)
        .one_or_none()
    )
    if trailer is None:
        raise HTTPException(status_code=404, detail="Trailer could not be persisted for this movie")

    existing: Optional[TrailerMediaDownload] = (
        s.query(TrailerMediaDownload)
        .filter(
            TrailerMediaDownload.media_item_id == trailer.id,
            TrailerMediaDownload.local_media_profile_id == profile.id,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.download_status not in _RESTARTABLE_STATUSES:
            raise HTTPException(status_code=409, detail=f"Trailer already has a download for profile '{profile.name}'")
        _reset_download(existing)
        s.flush()
        return existing

    download = TrailerMediaDownload(
        type=MediaType.TRAILER.value,
        media_item_id=trailer.id,
        local_media_profile_id=profile.id,
        download_status=MediaDownloadStatus.PENDING.value,
        file_path=str(resolve_movie_output_path(
            profile.output_template,
            movie=movie,
            media_item=trailer,
            append_media_type_to_filename=profile.append_media_type_to_filename,
        )),
        progress=0,
    )
    s.add(download)
    s.flush()
    return download


def _get_profile(s: Session, profile_id: int, expected_type: LocalMediaProfileType) -> LocalMediaProfileBase:
    profile: Optional[LocalMediaProfileBase] = s.get(LocalMediaProfileBase, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Local media profile not found")
    if profile.type != expected_type.value:
        label = "Movies and trailers" if expected_type == LocalMediaProfileType.MOVIE else "Episodes"
        raise HTTPException(status_code=422, detail=f"{label} require a {expected_type.value.title()} Local Media Profile")
    return profile


def _get_or_create_movie(s: Session, movie_data: DwMovieRecord) -> Movie:
    movie: Optional[Movie] = s.query(Movie).filter(Movie.slug == movie_data.slug).one_or_none()
    if movie is None:
        from backend.api.endpoints.movies.service import create_movie
        created = create_movie(s, _movie_create_from_dailywire(movie_data))
        movie = s.get(Movie, created.id)
        if movie is None:
            raise RuntimeError("Movie creation did not produce a persisted Movie record")
    return movie


def _movie_create_from_dailywire(movie_data: DwMovieRecord) -> MovieAPICreate:
    trailers: list[TrailerAPICreate] = []
    if movie_data.trailer is not None:
        trailers.append(TrailerAPICreate(
            dw_id=movie_data.trailer.dw_id,
            slug=movie_data.trailer.slug,
            title=movie_data.trailer.title,
            sharing_url=movie_data.trailer.sharing_url,
            duration=movie_data.trailer.duration,
            thumbnail_landscape_path=movie_data.trailer.thumbnail_landscape_path,
        ))

    return MovieAPICreate(
        dw_id=movie_data.dw_id,
        slug=movie_data.slug,
        title=movie_data.title,
        extended_title=movie_data.extended_title,
        description=movie_data.description,
        duration=movie_data.duration,
        background_image_path=movie_data.background_image_path,
        thumbnail_landscape_path=movie_data.thumbnail_landscape_path,
        thumbnail_portrait_path=movie_data.thumbnail_portrait_path,
        thumbnail_square_path=movie_data.thumbnail_square_path,
        sharing_url=movie_data.sharing_url,
        author_name=movie_data.author_name,
        author_slug=movie_data.author_slug,
        logo_image_path=movie_data.logo_image_path,
        mature_rating=movie_data.mature_rating,
        is_downloadable=movie_data.is_downloadable,
        available_for=movie_data.available_for,
        trailers=trailers,
    )


def retry_media_download(s: Session, media_download_id: int) -> MediaDownloadBase:
    download: Optional[MediaDownloadBase] = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    if download.download_status not in _RETRYABLE_STATUSES:
        raise HTTPException(status_code=409, detail="This download cannot be retried in its current state")

    if download.download_status in _CANCELLABLE_STATUSES:
        _record_cancellation(s, download, message=_USER_RESTART_MESSAGE)

    _reset_download(download)
    s.flush()
    return download


def cancel_media_download(s: Session, media_download_id: int) -> MediaDownloadBase:
    """Stop a queued/running download without scheduling a replacement."""
    download: Optional[MediaDownloadBase] = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    if download.download_status not in _CANCELLABLE_STATUSES:
        raise HTTPException(status_code=409, detail="This download is not currently in progress")

    _record_cancellation(s, download, message=_USER_CANCEL_MESSAGE)
    download.attempt_generation += 1
    download.download_status = MediaDownloadStatus.CANCELLED.value
    download.progress = 0
    download.error_message = None
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.started_at = None
    download.finished_at = datetime.now(timezone.utc)
    s.flush()
    remove_download_artifacts(download.file_path)
    return download


def _record_cancellation(s: Session, download: MediaDownloadBase, *, message: str) -> None:
    s.add(MediaDownloadAttempt(
        media_download_id=download.id,
        is_redownload=bool(getattr(download, "is_redownload_attempt", False) or False),
        status=MediaDownloadStatus.CANCELLED.value,
        error_message=message,
        downloaded_bytes=download.downloaded_bytes,
        format_downloaded=download.format_downloaded,
        started_at=download.started_at,
        finished_at=datetime.now(timezone.utc),
    ))


def _reset_download(download: MediaDownloadBase) -> None:
    download.attempt_generation += 1
    download.download_status = MediaDownloadStatus.PENDING.value
    download.progress = 0
    download.error_message = None
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.started_at = None
    download.finished_at = None


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
    payload = MediaDownloadAPIRead.model_validate(item)
    if item.download_status in _CANCELLABLE_STATUSES:
        # Removing the row invalidates every queued/running generation. Cleanup
        # is also repeated by an already-running worker when it notices this.
        remove_download_artifacts(item.file_path)
    s.delete(item)
    s.flush()
    return payload
