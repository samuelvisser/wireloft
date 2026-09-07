from fastapi import APIRouter, status

from .service import *
from ...models.episode import *
from ...models.media_download import EpisodeDownloadAPICreate
from ...models.operations import EpisodeMetadataOperationAccepted, MediaDownloadOperationAccepted, TaskOperationAccepted
from ..media_downloads.service import create_episode_download
from backend.app import db_session
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
)

router = APIRouter(prefix="/episodes", tags=["Episodes"])


@router.post(
    "/{episode_slug}/downloads",
    response_model=MediaDownloadOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def episode_download_create(episode_slug: str, body: EpisodeDownloadAPICreate):
    """Start an episode download as a generic UI TaskOperation."""
    with db_session() as s:
        try:
            download = create_episode_download(s, episode_slug, body)
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


@router.get("/by-show-slug/{show_slug}", response_model=list[EpisodeAPIRead])
def episodes_by_show_list(show_slug: str, limit: int | None = None):
    """
    List episodes for a specific show.

    Optional query parameter:
    - limit: maximum number of latest episodes to return (ordered by index desc).
    """
    with db_session() as s:
        return get_episodes_by_show_list(s, show_slug, limit)


@router.post("", response_model=EpisodeAPIRead, status_code=status.HTTP_201_CREATED)
def episode_create(body: EpisodeAPICreate):
    """
    Create a new episode for a show.

    Creates a new episode with the provided metadata and associates it with a show.
    Returns the created episode with a generated slug identifier.
    """
    with db_session() as s:
        try:
            result = create_episode(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{episode_slug}/refresh-metadata",
    response_model=EpisodeMetadataOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def episode_metadata_refresh(episode_slug: str):
    """Queue an immediate metadata refresh for one episode."""
    with db_session() as s:
        try:
            result = request_episode_metadata_refresh(s, episode_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{episode_slug}/early-delete",
    response_model=TaskOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def episode_early_delete(episode_slug: str):
    """Immediately remove one episode that is currently stuck in dw_processing."""
    with db_session() as s:
        try:
            result = request_episode_early_delete(s, episode_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_detail(episode_slug: str):
    with db_session() as s:
        return get_episode(s, episode_slug)


@router.patch("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_update(episode_slug: str, body: EpisodeAPIUpdate):
    with db_session() as s:
        try:
            result = update_episode(s, episode_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_delete(episode_slug: str):
    with db_session() as s:
        try:
            result = delete_episode(s, episode_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
