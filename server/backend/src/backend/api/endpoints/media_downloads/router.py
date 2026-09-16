from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from .actions import (
    cancel_media_download_action,
    delete_media_download_action,
    queue_bulk_media_download_operation,
    retry_media_download_action,
)
from .history import get_media_download_history
from .operations import (
    BulkCancelMediaDownloadsOperation,
    BulkDeleteMediaDownloadsOperation,
    BulkRetryMediaDownloadsOperation,
)
from .service import *
from ...models.media_download import *
from ...models.media_download_history import MediaDownloadHistoryPageRead
from ...models.operations import (
    MediaDownloadBulkOperationAccepted,
    MediaDownloadOperationAccepted,
)
from backend.app import db_session
from task_manager.tasks.media_download_operations import (
    dispatch_queued_media_download_operations,
    prioritize_media_download_operation,
)

router = APIRouter(prefix="/media-downloads", tags=["Media Downloads"])


@router.get("", response_model=list[MediaDownloadAPIRead])
def media_downloads_list():
    with db_session() as s:
        return get_media_downloads_list(s)


@router.get("/as-view", response_model=list[MediaDownloadAPIReadView])
def media_downloads_view(
        episode_slug: Optional[str] = None,
        movie_slug: Optional[str] = None,
        status_filter: Optional[list[str]] = Query(default=None, alias="status"),
        limit: Optional[int] = None,
):
    with db_session() as s:
        return get_media_downloads_view(
            s,
            episode_slug=episode_slug,
            movie_slug=movie_slug,
            statuses=status_filter,
            limit=limit,
        )


def _queue_bulk_operation(operation):
    with db_session() as s:
        try:
            result = queue_bulk_media_download_operation(s, operation)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/bulk/retry",
    response_model=MediaDownloadBulkOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def media_downloads_bulk_retry(body: MediaDownloadBulkActionAPIRequest):
    """Queue retries for the exact retryable rows selected by the Downloads page."""
    return _queue_bulk_operation(
        BulkRetryMediaDownloadsOperation(body.media_download_ids)
    )


@router.post(
    "/bulk/cancel",
    response_model=MediaDownloadBulkOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def media_downloads_bulk_cancel(body: MediaDownloadBulkActionAPIRequest):
    """Cancel the exact active rows selected by the Downloads page."""
    return _queue_bulk_operation(
        BulkCancelMediaDownloadsOperation(body.media_download_ids)
    )


@router.post(
    "/bulk/delete",
    response_model=MediaDownloadBulkOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def media_downloads_bulk_delete(body: MediaDownloadBulkActionAPIRequest):
    """Delete the exact rows selected by the Downloads page."""
    return _queue_bulk_operation(
        BulkDeleteMediaDownloadsOperation(body.media_download_ids)
    )


@router.post(
    "/{media_download_id}/retry",
    response_model=MediaDownloadOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def media_downloads_retry(media_download_id: int):
    """Start a replacement attempt using the generic operation pipeline."""
    operation_id = retry_media_download_action(media_download_id)
    return {
        "queued": True,
        "operation_id": operation_id,
        "media_download_id": media_download_id,
    }


@router.post(
    "/{media_download_id}/prioritize",
    response_model=MediaDownloadOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def media_downloads_prioritize(media_download_id: int):
    """Prioritize a queued download without replacing or restarting its attempt."""
    with db_session() as s:
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            raise HTTPException(status_code=404, detail="Media download not found")

        try:
            operation = prioritize_media_download_operation(s, media_download_id)
            # If a slot is already free, fill it now using the newly updated
            # ordering. Otherwise the terminal callback will honor this timestamp
            # when the next running download releases a slot.
            dispatch_queued_media_download_operations(s)
            operation_id = operation.id
            s.commit()
        except ValueError as exc:
            s.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            s.rollback()
            raise

    return {
        "queued": True,
        "operation_id": operation_id,
        "media_download_id": media_download_id,
    }


@router.post("/{media_download_id}/cancel", response_model=MediaDownloadAPIRead)
def media_downloads_cancel(media_download_id: int):
    """Cancel the active media.download operation and suppress automatic requeue."""
    return cancel_media_download_action(media_download_id)


@router.get("/{media_download_id}/history", response_model=MediaDownloadHistoryPageRead)
def media_downloads_history(
        media_download_id: int,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
):
    """Return download TaskRun history enriched with the current artifact problem."""
    with db_session() as s:
        return get_media_download_history(
            s,
            media_download_id,
            offset=offset,
            limit=limit,
        )


@router.get("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_detail(media_download_id: int):
    with db_session() as s:
        return get_media_download(s, media_download_id)


@router.patch("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_update(media_download_id: int, body: MediaDownloadAPIUpdate):
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
    """Delete the domain artifact record and all scheduler work it owns."""
    return delete_media_download_action(media_download_id)
