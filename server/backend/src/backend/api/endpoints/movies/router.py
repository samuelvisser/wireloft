from fastapi import APIRouter, HTTPException, status

from .service import *
from ...models.movie import *
from ...models.media_download import MediaDownloadAPIRead, MovieDownloadAPICreate
from ..dailywire.movies.service import get_movie as get_dailywire_movie
from ..media_downloads.router import _trigger_download_task
from ..media_downloads.service import create_movie_download, create_trailer_download
from backend.app import db_session

router = APIRouter(prefix="/movies", tags=["Movies"])


@router.post("/{movie_slug}/downloads", response_model=MediaDownloadAPIRead, status_code=status.HTTP_201_CREATED)
def movie_download_create(movie_slug: str, body: MovieDownloadAPICreate):
    """Persist a browsed Daily Wire movie and start its manual download."""
    try:
        movie_data = get_dailywire_movie(movie_slug)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with db_session() as s:
        try:
            download = create_movie_download(s, movie_data, body)
            payload = MediaDownloadAPIRead.model_validate(download)
            movie_id = download.media_item_id
            attempt_generation = download.attempt_generation
            s.commit()
        except Exception:
            s.rollback()
            raise

    _trigger_download_task(
        media_download_id=payload.id,
        media_item_id=movie_id,
        media_type="movie",
        attempt_generation=attempt_generation,
    )
    return payload


@router.post(
    "/{movie_slug}/trailers/{trailer_slug}/downloads",
    response_model=MediaDownloadAPIRead,
    status_code=status.HTTP_201_CREATED,
)
def trailer_download_create(movie_slug: str, trailer_slug: str, body: MovieDownloadAPICreate):
    """Persist a browsed Daily Wire trailer and download it with a Movie profile."""
    try:
        movie_data = get_dailywire_movie(movie_slug)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with db_session() as s:
        try:
            download = create_trailer_download(s, movie_data, trailer_slug, body)
            payload = MediaDownloadAPIRead.model_validate(download)
            trailer_id = download.media_item_id
            attempt_generation = download.attempt_generation
            s.commit()
        except Exception:
            s.rollback()
            raise

    _trigger_download_task(
        media_download_id=payload.id,
        media_item_id=trailer_id,
        media_type="trailer",
        attempt_generation=attempt_generation,
    )
    return payload


@router.get("", response_model=list[MovieAPIRead])
def movie_list():
    """List all movies in the system."""
    with db_session() as s:
        return get_movies_list(s)


@router.post("", response_model=MovieAPIRead, status_code=status.HTTP_201_CREATED)
def movie_create(body: MovieAPICreate):
    """Create a new movie entry."""
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
    """Retrieve detailed information for a specific movie."""
    with db_session() as s:
        return get_movie(s, movie_slug)


@router.patch("/{movie_slug}", response_model=MovieAPIRead)
def movie_update(movie_slug: str, body: MovieAPIUpdate):
    """Update an existing movie's metadata."""
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
    """Delete a movie from the system."""
    with db_session() as s:
        try:
            result = delete_movie(s, movie_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
