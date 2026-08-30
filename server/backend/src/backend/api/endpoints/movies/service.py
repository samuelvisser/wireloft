from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.movie import *
from backend.db.models.media_item import Movie
from backend.api.endpoints.trailers.service import create_trailer
from backend.integrations.tmdb import lookup_movie_release_metadata


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


def create_movie(s: Session, body: MovieAPICreate) -> MovieAPIRead:
    data = body.model_dump(by_alias=True, exclude={"trailers"})
    item = Movie(**data)
    s.add(item)
    s.flush()

    # The Daily Wire API has no canonical release date. Perform one external
    # metadata lookup at the moment this movie is first persisted, then store
    # both the result and the terminal lookup state on the movie row. Movie and
    # trailer download entry points both reach this service through the same
    # _get_or_create_movie flow.
    lookup = lookup_movie_release_metadata(
        title=item.title,
        description=item.description,
        duration_seconds=item.duration,
    )
    if lookup is not None:
        item.release_date = lookup.release_date
        item.release_date_source = lookup.source
        item.release_date_source_id = lookup.source_id
        item.release_date_lookup_status = lookup.status
        item.release_date_lookup_attempted_at = lookup.attempted_at
        item.release_date_lookup_error = lookup.error
        s.flush()

    for trailer in body.trailers:
        create_trailer(s, item.id, trailer)

    # Movie, trailers and any calling operation remain in the caller's single
    # transaction. Services flush only; routers own commit and rollback.
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
    s.delete(item)
    s.flush()
    return payload
