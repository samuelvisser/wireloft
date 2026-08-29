from fastapi import APIRouter, status

from .service import *
from ...models.episode import *
from ...models.media_download import EpisodeDownloadAPICreate, MediaDownloadAPIRead
from ..media_downloads.service import create_episode_download
from ..media_downloads.router import _trigger_download_task
from backend.app import db_session

router = APIRouter(prefix="/episodes", tags=["Episodes"])


@router.post("/{episode_slug}/downloads", response_model=MediaDownloadAPIRead, status_code=status.HTTP_201_CREATED)
def episode_download_create(episode_slug: str, body: EpisodeDownloadAPICreate):
    """
    Start downloading an episode according to a Local Media Profile.

    Creates the download record and queues the download task. Each episode can
    have at most one download per Local Media Profile; a pending or errored
    download for the same profile is restarted instead.
    """
    with db_session() as s:
        try:
            download = create_episode_download(s, episode_slug, body)
            payload = MediaDownloadAPIRead.model_validate(download)
            episode_id = download.media_item_id
            attempt_generation = download.attempt_generation
            s.commit()
        except Exception:
            s.rollback()
            raise

    _trigger_download_task(
        media_download_id=payload.id,
        media_item_id=episode_id,
        media_type="episode",
        attempt_generation=attempt_generation,
    )
    return payload

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


@router.get("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_detail(episode_slug: str):
    """
    Retrieve detailed information for a specific episode.

    Returns complete episode metadata including title, description, and associated media.
    """
    with db_session() as s:
        return get_episode(s, episode_slug)


@router.patch("/{episode_slug}", response_model=EpisodeAPIRead)
def episode_update(episode_slug: str, body: EpisodeAPIUpdate):
    """
    Update an existing episode's metadata.

    Partially updates episode information with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
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
    """
    Delete an episode from the system.

    Permanently removes the specified episode and its associated data.
    Returns the deleted episode's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_episode(s, episode_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
