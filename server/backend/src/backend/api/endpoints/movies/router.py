from fastapi import APIRouter, status

from .service import *
from ...models.movie import MovieAPIRead

router = APIRouter()

@router.get("", response_model=list[MovieAPIRead])
def movie_list():
    return get_movies_list()


@router.post("", response_model=MovieAPIRead, status_code=status.HTTP_201_CREATED)
def movie_create(body: MovieAPICreate):
    return create_movie(body)


@router.get("/{movie_slug}", response_model=MovieAPIRead)
def movie_detail(movie_slug: str):
    return get_movie(movie_slug)


@router.patch("/{movie_slug}", response_model=MovieAPIRead)
def movie_update(movie_slug: str, body: MovieAPIUpdate):
    return update_movie(movie_slug, body)


@router.delete("/{movie_slug}", response_model=MovieAPIRead)
def movie_delete(movie_slug: str):
    return delete_movie(movie_slug)
