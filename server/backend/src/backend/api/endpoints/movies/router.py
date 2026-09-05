from fastapi import APIRouter, HTTPException, status

from .service import *
from ...models.movie import *
from ...models.media_download import MovieDownloadAPICreate
from ...models.operations import MediaDownloadOperationAccepted, TaskOperationAccepted
from ..dailywire.movies.service import get_movie_for_action as get_dailywire_movie
from ..media_downloads.service import create_movie_download, create_movie_extra_download
from backend.app import db_session
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
)

router = APIRouter(prefix="/movies", tags=["Movies"])


@router.post("/{movie_slug}/index", response_model=MovieAPIRead, status_code=status.HTTP_201_CREATED)
def movie_index(movie_slug: str):
    """Index a browsed Daily Wire movie and its extras without downloading anything."""
    try:
        movie_data = get_dailywire_movie(movie_slug)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with db_session() as s:
        try:
            movie, _ = index_dailywire_movie(s, movie_data)
            payload = MovieAPIRead.model_validate(movie)
            s.commit()
            return payload
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{movie_slug}/downloads",
    response_model=MediaDownloadOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def movie_download_create(movie_slug: str, body: MovieDownloadAPICreate):
    """Persist a movie artifact target and start it as a generic UI operation."""
    try:
        movie_data = get_dailywire_movie(movie_slug)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with db_session() as s:
        try:
            download = create_movie_download(s, movie_data, body)
            operation = create_media_download_operation(
                s,
                download,
                source=OperationSource.UI.value,
            )
            dispatch_queued_media_download_operations(s)
            result = {
                "queued": True,
                "operation_id": operation.id,
                "media_download_id": download.id,
            }
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{movie_slug}/extras/{movie_extra_slug}/downloads",
    response_model=MediaDownloadOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def movie_extra_download_create(movie_slug: str, movie_extra_slug: str, body: MovieDownloadAPICreate):
    """Persist a movie-extra artifact target and start it as a generic UI operation."""
    try:
        movie_data = get_dailywire_movie(movie_slug)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with db_session() as s:
        try:
            download = create_movie_extra_download(s, movie_data, movie_extra_slug, body)
            operation = create_media_download_operation(
                s,
                download,
                source=OperationSource.UI.value,
            )
            dispatch_queued_media_download_operations(s)
            result = {
                "queued": True,
                "operation_id": operation.id,
                "media_download_id": download.id,
            }
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{movie_slug}/extras/refresh",
    response_model=TaskOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def movie_extras_refresh(movie_slug: str):
    """Queue a UI-visible refresh that indexes newly published movie extras."""
    with db_session() as s:
        try:
            result = request_movie_extras_refresh(s, movie_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


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


@router.post("/{movie_slug}/release-metadata/retry", response_model=MovieAPIRead)
def movie_release_metadata_retry(movie_slug: str):
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
