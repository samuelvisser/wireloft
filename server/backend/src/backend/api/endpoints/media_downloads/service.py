from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.media_download import *
from backend.db.models import Episode, LocalMediaProfileBase, Movie, Show
from backend.db.models.media_download import (
    EpisodeMediaDownload,
    MediaDownloadAttempt,
    MediaDownloadBase,
    MovieMediaDownload,
)
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import LocalMediaProfileType
from backend.types.media_types import MediaType
from backend.utils.output_template import resolve_episode_output_path, resolve_movie_output_path

# Statuses that are safe to restart or replace: nothing is actively running
_RESTARTABLE_STATUSES = {
    MediaDownloadStatus.PENDING.value,
    MediaDownloadStatus.ERROR.value,
    MediaDownloadStatus.MISSING.value,
    MediaDownloadStatus.CORRUPTED.value,
}


def get_media_downloads_list(s: Session) -> list[MediaDownloadAPIRead]:
    items = (
        s.query(MediaDownloadBase)
        .order_by(MediaDownloadBase.id)
        .all()
    )
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
        movie = media if isinstance(media, Movie) else None
        if episode_slug is not None and (episode is None or episode.slug != episode_slug):
            continue
        if movie_slug is not None and (movie is None or movie.slug != movie_slug):
            continue
        show = episode.show if episode else None
        base = MediaDownloadAPIRead.model_validate(download)
        views.append(MediaDownloadAPIReadView(
            **base.model_dump(by_alias=False),
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
    """A download's full attempt ledger, newest first."""
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
    item = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    return MediaDownloadAPIRead.model_validate(item)


def create_episode_download(s: Session, episode_slug: str, body: EpisodeDownloadAPICreate) -> EpisodeMediaDownload:
    """Create the download row for (episode, local media profile).

    Only one download per profile is allowed for an episode. An existing
    pending/errored row is reused (restarted); an active or finished one is a conflict.
    """
    episode: Optional[Episode] = (
        s.query(Episode).filter(Episode.slug == episode_slug).one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if episode.is_no_show_today:
        raise HTTPException(status_code=422, detail="This is not a downloadable episode")

    profile: Optional[LocalMediaProfileBase] = s.get(LocalMediaProfileBase, body.local_media_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Local media profile not found")
    if profile.type != LocalMediaProfileType.SHOW.value:
        raise HTTPException(status_code=422, detail="Episodes require a Show Local Media Profile")

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
            raise HTTPException(
                status_code=409,
                detail=f"Episode already has a download for profile '{profile.name}'",
            )
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
    movie_data,
    body: MovieDownloadAPICreate,
) -> MovieMediaDownload:
    """Upsert a browsed Daily Wire movie and queue its manual download."""
    profile: Optional[LocalMediaProfileBase] = s.get(LocalMediaProfileBase, body.local_media_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Local media profile not found")
    if profile.type != LocalMediaProfileType.MOVIE.value:
        raise HTTPException(status_code=422, detail="Movies require a Movie Local Media Profile")
    if not movie_data.is_downloadable:
        raise HTTPException(status_code=422, detail="Daily Wire marks this movie as unavailable for download")

    movie: Optional[Movie] = s.query(Movie).filter(Movie.slug == movie_data.slug).one_or_none()
    values = {
        "dw_id": movie_data.dw_id,
        "slug": movie_data.slug,
        "title": movie_data.title,
        "extended_title": movie_data.extended_title,
        "description": movie_data.description,
        "duration": movie_data.duration,
        "background_image_path": movie_data.background_image_path,
        "thumbnail_landscape_path": movie_data.thumbnail_landscape_path,
        "thumbnail_portrait_path": movie_data.thumbnail_portrait_path,
        "thumbnail_square_path": movie_data.thumbnail_square_path,
        "sharing_url": movie_data.sharing_url,
        "author_name": movie_data.author_name,
        "mature_rating": movie_data.mature_rating,
        "is_downloadable": movie_data.is_downloadable,
        "trailer_slug": movie_data.trailer.slug if movie_data.trailer else None,
        "trailer_title": movie_data.trailer.title if movie_data.trailer else None,
        "trailer_sharing_url": movie_data.trailer.sharing_url if movie_data.trailer else None,
        "trailer_thumbnail_path": movie_data.trailer.thumbnail_landscape_path if movie_data.trailer else None,
    }
    if movie is None:
        from backend.utils.helpers import generate_uuid

        movie = Movie(uuid=generate_uuid(), type=MediaType.MOVIE.value, downloaded_date=None, **values)
        s.add(movie)
        s.flush()
    else:
        for key, value in values.items():
            setattr(movie, key, value)

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
        file_path=str(resolve_movie_output_path(profile.output_template, movie=movie)),
        progress=0,
    )
    s.add(download)
    s.flush()
    return download


def retry_media_download(s: Session, media_download_id: int) -> MediaDownloadBase:
    """Reset an errored download so it can be started again."""
    download: Optional[MediaDownloadBase] = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise HTTPException(status_code=404, detail="Media download not found")
    if download.download_status not in _RESTARTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Only pending or errored downloads can be retried")

    _reset_download(download)
    s.flush()
    return download


def _reset_download(download: MediaDownloadBase) -> None:
    download.download_status = MediaDownloadStatus.PENDING.value
    download.progress = 0
    download.error_message = None
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.started_at = None
    download.finished_at = None


def update_media_download(s: Session, media_download_id: int, body: MediaDownloadAPIUpdate) -> MediaDownloadAPIRead:
    item: Optional[MediaDownloadBase] = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    update_database_fields(item, body)
    s.flush()
    return MediaDownloadAPIRead.model_validate(item)


def delete_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    if item.download_status == MediaDownloadStatus.DOWNLOADING.value:
        raise HTTPException(status_code=409, detail="Cannot delete a download that is currently running")

    payload = MediaDownloadAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
