from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.movie import *
from backend.db.models.media_download import MediaDownloadBase
from backend.db.models.media_item import Movie
from backend.api.endpoints.trailers.service import create_trailer
from backend.integrations.tmdb import MovieReleaseLookupResult, lookup_movie_release_metadata


def get_movies_list(s: Session) -> list[MovieAPIRead]:
    items = (
        s.query(Movie)
        .order_by(Movie.title.asc())
        .all()
    )
    return [MovieAPIRead.model_validate(it) for it in items]


def get_movie(s: Session, movie_slug: str) -> MovieAPIRead:
    item = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    return MovieAPIRead.model_validate(item)


def _apply_movie_release_lookup(item: Movie, lookup: MovieReleaseLookupResult) -> None:
    item.release_date = lookup.release_date
    item.release_date_source = lookup.source
    item.release_date_source_id = lookup.source_id
    item.release_date_lookup_status = lookup.status
    item.release_date_lookup_attempted_at = lookup.attempted_at
    item.release_date_lookup_error = lookup.error


def ensure_movie_release_metadata(s: Session, item: Movie) -> None:
    """Run at most one configured release-date lookup for a persisted movie."""
    if item.release_date_lookup_attempted_at is not None:
        return

    lookup = lookup_movie_release_metadata(
        title=item.title,
        description=item.description,
        duration_seconds=item.duration,
    )
    # A missing token is not counted as an attempt. This lets a movie that was
    # added before TMDB was configured receive its one lookup on the next movie
    # or trailer download request.
    if lookup is None:
        return

    _apply_movie_release_lookup(item, lookup)
    s.flush()


def retry_movie_release_metadata(s: Session, movie_slug: str) -> MovieAPIRead:
    """Retry a transient TMDB lookup failure for an already-persisted movie."""
    item: Optional[Movie] = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    if item.release_date_lookup_status != "error":
        raise HTTPException(
            status_code=409,
            detail="TMDB release metadata can only be retried after a lookup error",
        )

    lookup = lookup_movie_release_metadata(
        title=item.title,
        description=item.description,
        duration_seconds=item.duration,
    )
    if lookup is None:
        raise HTTPException(
            status_code=422,
            detail="Configure a TMDB API Read Access Token before retrying movie release metadata",
        )

    _apply_movie_release_lookup(item, lookup)
    s.flush()
    return MovieAPIRead.model_validate(item)


def create_movie(s: Session, body: MovieAPICreate) -> MovieAPIRead:
    data = body.model_dump(by_alias=True, exclude={"trailers"})
    item = Movie(**data)
    s.add(item)
    s.flush()

    for trailer in body.trailers:
        create_trailer(s, item.id, trailer)

    # Movie, trailers and any calling operation remain in the caller's single
    # transaction. Services flush only; routers own commit and rollback. The
    # Daily Wire browser download flow performs release metadata enrichment in
    # _get_or_create_movie, not for arbitrary direct API-created movies.
    return MovieAPIRead.model_validate(item)


def update_movie(s: Session, movie_slug: str, body: MovieAPIUpdate) -> MovieAPIRead:
    item: Optional[Movie] = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    update_database_fields(item, body)
    s.flush()
    return MovieAPIRead.model_validate(item)


def delete_movie(s: Session, movie_slug: str) -> MovieAPIRead:
    item = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    payload = MovieAPIRead.model_validate(item)

    # Route every Movie and Trailer download through the normal deletion
    # service before removing their media records. Active downloads are thereby
    # cancelled and their partial artifacts removed, while completed files are
    # deliberately left on disk.
    media_item_ids = [item.id, *(trailer.id for trailer in item.trailers)]
    download_ids = list(s.scalars(
        select(MediaDownloadBase.id).where(
            MediaDownloadBase.media_item_id.in_(media_item_ids),
        )
    ))
    from backend.api.endpoints.media_downloads.service import delete_media_download
    for download_id in download_ids:
        delete_media_download(s, download_id)

    s.delete(item)
    s.flush()
    return payload
