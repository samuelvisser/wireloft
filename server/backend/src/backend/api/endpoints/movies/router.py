from fastapi import APIRouter, status

from .service import *
from ...models.movie import *
from backend.app import db_session

router = APIRouter(prefix="/movies", tags=["Movies"])

@router.get("", response_model=list[MovieAPIRead])
def movie_list():
    """
    List all movies in the system.

    Returns a collection of all movie records with their metadata.
    """
    with db_session() as s:
        return get_movies_list(s)


@router.post("", response_model=MovieAPIRead, status_code=status.HTTP_201_CREATED)
def movie_create(body: MovieAPICreate):
    """
    Create a new movie entry.

    Adds a new movie to the system with the provided metadata.
    Returns the created movie with a generated slug identifier.
    """
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
    """
    Retrieve detailed information for a specific movie.

    Returns complete movie metadata including title, description, and associated media.
    """
    with db_session() as s:
        return get_movie(s, movie_slug)


@router.patch("/{movie_slug}", response_model=MovieAPIRead)
def movie_update(movie_slug: str, body: MovieAPIUpdate):
    """
    Update an existing movie's metadata.

    Partially updates movie information with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
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
    """
    Delete a movie from the system.

    Permanently removes the specified movie and its associated data.
    Returns the deleted movie's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_movie(s, movie_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
