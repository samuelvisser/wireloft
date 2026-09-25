from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.endpoints.movie_extras.service import create_movie_extra
from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.api.models.movie import *
from backend.db.models.media_item import Movie
from backend.integrations.tmdb import lookup_movie_release_metadata
from backend.types.media_types import MediaType
from backend.services.movies import (
    DAILYWIRE_RELEASE_SOURCE,
    apply_movie_release_lookup,
    index_dailywire_movie,
    sync_indexed_dailywire_movie,
)
from dailywire_api.records import DwMovieRecord
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import queue_operation_target_dispatch

from .operations import MovieExtrasRefreshOperation


def get_movies_list(s: Session) -> list[MovieAPIRead]:
    items = s.query(Movie).order_by(Movie.title.asc()).all()
    return [MovieAPIRead.model_validate(it) for it in items]


def get_movie(s: Session, movie_slug: str) -> MovieAPIRead:
    item = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return MovieAPIRead.model_validate(item)


def request_movie_extras_refresh(s: Session, movie_slug: str) -> dict[str, bool | str]:
    """Queue a UI-visible movie-extra refresh through the TaskOperation pipeline."""
    movie: Optional[Movie] = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    operation = create_operation(s, MovieExtrasRefreshOperation(movie))
    queue_operation_target_dispatch(s, operation.id, operation.targets[0].slot_key)
    return {"queued": True, "operation_id": operation.id}


def retry_movie_release_metadata(s: Session, movie_slug: str) -> MovieAPIRead:
    """Retry a transient TMDB lookup failure for an already-persisted movie."""
    item: Optional[Movie] = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    if item.release_date_source == DAILYWIRE_RELEASE_SOURCE:
        raise HTTPException(
            status_code=409,
            detail="Daily Wire already supplies this movie's release date",
        )
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

    apply_movie_release_lookup(item, lookup)
    s.flush()
    return MovieAPIRead.model_validate(item)


def create_movie(s: Session, body: MovieAPICreate) -> MovieAPIRead:
    item = create_database_fields(
        Movie,
        body,
        exclude_fields={"movie_extras", "official_trailer_slug"},
    )
    item.type = MediaType.MOVIE.value
    s.add(item)
    s.flush()

    for movie_extra in body.movie_extras:
        create_movie_extra(s, item.id, movie_extra)

    if body.official_trailer_slug is not None:
        official_trailer = next(
            (extra for extra in item.movie_extras if extra.slug == body.official_trailer_slug),
            None,
        )
        if official_trailer is None:
            raise ValueError("The official trailer must be included in movie_extras")
        item.official_trailer = official_trailer
        s.flush()

    return MovieAPIRead.model_validate(item)


def refresh_dailywire_movie(
    s: Session,
    movie_slug: str,
    movie_data: DwMovieRecord,
) -> MovieAPIRead:
    """Refresh a movie that is already indexed without ever creating a new row."""
    item: Optional[Movie] = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    sync_indexed_dailywire_movie(s, movie=item, movie_data=movie_data)
    return MovieAPIRead.model_validate(item)


def update_movie(s: Session, movie_slug: str, body: MovieAPIUpdate) -> MovieAPIRead:
    item: Optional[Movie] = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    update_database_fields(item, body)
    s.flush()
    return MovieAPIRead.model_validate(item)


def delete_movie(s: Session, movie_slug: str) -> MovieAPIRead:
    item = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    payload = MovieAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
