from fastapi import APIRouter, HTTPException, status

from .service import *
from ...models.movie import *
from ...models.media_download import MediaDownloadAPIRead, MovieDownloadAPICreate
from ..dailywire.movies.service import get_movie as get_dailywire_movie
from ..media_downloads.router import _trigger_download_task
from ..media_downloads.service import create_movie_download, create_movie_extra_download
from backend.app import db_session
from backend.db.models import Movie
from backend.utils.output_template import MovieReleaseDateUnavailableError

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
        except MovieReleaseDateUnavailableError as exc:
            # The profile cannot be resolved, but retaining the movie and the
            # terminal lookup result makes the external lookup truly one-time.
            # No download row has been added at the point this error is raised.
            s.commit()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    "/{movie_slug}/extras/{movie_extra_slug}/downloads",
    response_model=MediaDownloadAPIRead,
    status_code=status.HTTP_201_CREATED,
)
def movie_extra_download_create(movie_slug: str, movie_extra_slug: str, body: MovieDownloadAPICreate):
    """Persist a browsed Daily Wire movie extra and download it with a Movie profile."""
    try:
        movie_data = get_dailywire_movie(movie_slug)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with db_session() as s:
        try:
            download = create_movie_extra_download(s, movie_data, movie_extra_slug, body)
            payload = MediaDownloadAPIRead.model_validate(download)
            movie_extra_id = download.media_item_id
            attempt_generation = download.attempt_generation
            s.commit()
        except MovieReleaseDateUnavailableError as exc:
            # Keep the parent movie, extra and lookup result even though this
            # particular profile cannot create a safe release-dated path.
            s.commit()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception:
            s.rollback()
            raise

    _trigger_download_task(
        media_download_id=payload.id,
        media_item_id=movie_extra_id,
        media_type="movie_extra",
        attempt_generation=attempt_generation,
    )
    return payload


@router.post("/{movie_slug}/extras/refresh", status_code=status.HTTP_202_ACCEPTED)
def movie_extras_refresh(movie_slug: str):
    """Queue a manual refresh that indexes newly published movie extras."""
    with db_session() as s:
        movie = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
        if movie is None:
            raise HTTPException(status_code=404, detail="Movie not found")
        movie_id = movie.id

    from task_manager.scheduler.executor import trigger_now

    job_id = trigger_now(
        def_key="refresh_movie_extras",
        resource_type="movie",
        resource_id=movie_id,
    )
    return {"jobId": job_id}


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


@router.post("/{movie_slug}/release-metadata/retry", response_model=MovieAPIRead)
def movie_release_metadata_retry(movie_slug: str):
    """Retry a TMDB release-date lookup that previously failed with an error."""
    with db_session() as s:
        try:
            result = retry_movie_release_metadata(s, movie_slug)
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
