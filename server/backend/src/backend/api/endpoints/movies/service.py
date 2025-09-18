from __future__ import annotations

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.movie import *
from backend.app import db_session
from backend.db.models import Movie


def get_movies_list() -> list[MovieAPIRead]:
    with db_session() as s:
        items = (
            s.query(Movie)
            .order_by(Movie.title.asc())
            .all()
        )
        return [MovieAPIRead.model_construct(it) for it in items]


def get_movie(movie_slug: str) -> MovieAPIRead:
    with db_session() as s:
        item = (
            s.query(Movie)
            .filter(Movie.slug == movie_slug)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Movie not found")

        return MovieAPIRead.model_construct(item)


def create_movie(body: MovieAPICreate) -> MovieAPIRead:
    with db_session() as s:
        data = body.model_dump(by_alias=True)
        item = Movie(**data)
        s.add(item)
        s.commit()
        s.refresh(item)
        return MovieAPIRead.model_construct(item)


def update_movie(movie_slug: str, body: MovieAPIUpdate) -> MovieAPIRead:
    with db_session() as s:
        item = (
            s.query(Movie)
            .filter(Movie.slug == movie_slug)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Movie not found")

        update_database_fields(item, body)
        s.commit()
        s.refresh(item)
        return MovieAPIRead.model_construct(item)


def delete_movie(movie_slug: str) -> MovieAPIRead:
    with db_session() as s:
        item = (
            s.query(Movie)
            .filter(Movie.slug == movie_slug)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Movie not found")

        payload = MovieAPIRead.model_construct(item)
        s.delete(item)
        s.commit()
        return payload
