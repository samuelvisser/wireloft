from fastapi import APIRouter, status

from .service import *
from ...models.movie import *
from backend.app import db_session

router = APIRouter(prefix="/movies", tags=["Movies"])

@router.get("", response_model=list[MovieAPIRead])
def movie_list():
    with db_session() as s:
        return get_movies_list(s)


@router.post("", response_model=MovieAPIRead, status_code=status.HTTP_201_CREATED)
def movie_create(body: MovieAPICreate):
    with db_session() as s:
        try:
            result = create_movie(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{movie_slug}", response_model=MovieAPIRead)
def movie_detail(movie_slug: str):
    with db_session() as s:
        return get_movie(s, movie_slug)


@router.patch("/{movie_slug}", response_model=MovieAPIRead)
def movie_update(movie_slug: str, body: MovieAPIUpdate):
    with db_session() as s:
        try:
            result = update_movie(s, movie_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{movie_slug}", response_model=MovieAPIRead)
def movie_delete(movie_slug: str):
    with db_session() as s:
        try:
            result = delete_movie(s, movie_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
