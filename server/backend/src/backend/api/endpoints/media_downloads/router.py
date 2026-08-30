from typing import Optional

from fastapi import APIRouter, Query, status

from .service import *
from ...models.media_download import *
from backend.app import db_session

router = APIRouter(prefix="/media-downloads", tags=["Media Downloads"])

@router.get("", response_model=list[MediaDownloadAPIRead])
def media_downloads_list():
    """
    List all media downloads in the system.

    Returns a collection of all media download records including status and progress.
    """
    with db_session() as s:
        return get_media_downloads_list(s)


@router.get("/as-view", response_model=list[MediaDownloadAPIReadView])
def media_downloads_view(
        episode_slug: Optional[str] = None,
        movie_slug: Optional[str] = None,
        status_filter: Optional[list[str]] = Query(default=None, alias="status"),
        limit: Optional[int] = None,
):
    """
    List media downloads joined with their episode, show and profile context.

    Optional query parameters:
    - episode_slug: only downloads of this episode
    - status: repeatable; only downloads in these statuses (e.g. downloading, error)
    - limit: maximum number of rows, newest first
    """
    with db_session() as s:
        return get_media_downloads_view(
            s,
            episode_slug=episode_slug,
            movie_slug=movie_slug,
            statuses=status_filter,
            limit=limit,
        )


@router.post("/{media_download_id}/retry", response_model=MediaDownloadAPIRead)
def media_downloads_retry(media_download_id: int):
    """
    Restart a queued, active, or failed download.

    Advances its attempt generation so an existing worker cancels, resets the
    download record, and queues a fresh worker for the same item and profile.
    """
    with db_session() as s:
        try:
            download = retry_media_download(s, media_download_id)
            payload = MediaDownloadAPIRead.model_validate(download)
            media_item_id = download.media_item_id
            media_type = download.type
            attempt_generation = download.attempt_generation
            s.commit()
        except Exception:
            s.rollback()
            raise

    _trigger_download_task(
        media_download_id=payload.id,
        media_item_id=media_item_id,
        media_type=media_type,
        attempt_generation=attempt_generation,
    )
    return payload


@router.post("/{media_download_id}/cancel", response_model=MediaDownloadAPIRead)
def media_downloads_cancel(media_download_id: int):
    """Cancel a queued or running download without starting another attempt."""
    with db_session() as s:
        try:
            download = cancel_media_download(s, media_download_id)
            payload = MediaDownloadAPIRead.model_validate(download)
            s.commit()
            return payload
        except Exception:
            s.rollback()
            raise


@router.get("/{media_download_id}/attempts", response_model=list[MediaDownloadAttemptAPIRead])
def media_downloads_attempts(media_download_id: int):
    """
    List a download's full attempt ledger, newest first.

    Every completed attempt (successful or not) is recorded permanently here,
    so a previous error is never lost just because a retry was started.
    """
    with db_session() as s:
        return get_media_download_attempts(s, media_download_id)


@router.get("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_detail(media_download_id: int):
    """
    Retrieve detailed information for a specific media download.

    Returns complete download information including status, progress, and file location.
    """
    with db_session() as s:
        return get_media_download(s, media_download_id)


@router.patch("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_update(media_download_id: int, body: MediaDownloadAPIUpdate):
    """
    Update an existing media download's metadata or status.

    Partially updates download information with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
    with db_session() as s:
        try:
            result = update_media_download(s, media_download_id, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_delete(media_download_id: int):
    """
    Delete a media download record from the system.

    Permanently removes the download record. A queued/running download is
    cancelled and its partial artifacts are removed first. Completed files are
    left on disk.
    Returns the deleted download's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_media_download(s, media_download_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


def _trigger_download_task(
        *,
        media_download_id: int,
        media_item_id: int,
        media_type: str,
        attempt_generation: int,
) -> None:
    """Queue the download worker for a freshly created/reset download row."""
    from task_manager.scheduler.executor import trigger_now

    if media_type == "movie":
        trigger_now(
            def_key="download_movie",
            resource_type="movie",
            resource_id=media_item_id,
            media_download_id=media_download_id,
            attempt_generation=attempt_generation,
        )
        return

    trigger_now(
        def_key="download_episode",
        resource_type="episode",
        resource_id=media_item_id,
        media_download_id=media_download_id,
        attempt_generation=attempt_generation,
    )
