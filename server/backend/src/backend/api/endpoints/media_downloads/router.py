from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from .service import *
from ...models.media_download import *
from ...models.operations import MediaDownloadOperationAccepted
from backend.app import db_session
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
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


@router.post(
    "/{media_download_id}/retry",
    response_model=MediaDownloadOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def media_downloads_retry(media_download_id: int):
    """Start a replacement attempt using the generic operation pipeline."""
    active_operation_id: str | None = None
    is_redownload = False
    with db_session() as s:
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            raise HTTPException(status_code=404, detail="Media download not found")
        active = get_active_media_download_operation(s, media_download_id)
        if active is not None:
            active_operation_id = active.id
        # Capture this before retry_media_download clears the old artifact facts.
        # A missing/corrupt artifact still represents a replacement of something
        # WireLoft previously downloaded, so keep the redownload audit semantics.
        is_redownload = (
            download.downloaded_at is not None
            or download.artifact_status in {"available", "missing", "corrupted"}
        )

    if active_operation_id is not None:
        cancel_operation(
            active_operation_id,
            reason="Replaced by retry",
            acknowledge=True,
        )

    with db_session() as s:
        try:
            download = retry_media_download(s, media_download_id)
            operation = create_media_download_operation(
                s,
                download,
                source=OperationSource.UI.value,
                is_redownload=is_redownload,
            )
            dispatch_queued_media_download_operations(s)
            operation_id = operation.id
            s.commit()
            return {
                "queued": True,
                "operation_id": operation_id,
                "media_download_id": media_download_id,
            }
        except Exception:
            s.rollback()
            raise


@router.post("/{media_download_id}/cancel", response_model=MediaDownloadAPIRead)
def media_downloads_cancel(media_download_id: int):
    """Cancel the active media.download operation and suppress automatic requeue."""
    with db_session() as s:
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            raise HTTPException(status_code=404, detail="Media download not found")
        operation = get_active_media_download_operation(s, media_download_id)
        if operation is None:
            raise HTTPException(status_code=409, detail="This download is not currently in progress")
        operation_id = operation.id

    try:
        cancel_operation(operation_id, reason="Canceled by user", acknowledge=True)
    except ValueError as exc:
        # The worker may have completed between the read above and the durable
        # cancellation transaction. Treat that as a normal state race, not a 500.
        raise HTTPException(status_code=409, detail="This download is not currently in progress") from exc

    with db_session() as s:
        try:
            download = s.get(MediaDownloadBase, media_download_id)
            if download is None:
                raise HTTPException(status_code=404, detail="Media download not found")

            # Persist the user's intent after cancellation. A Download Profile
            # sweep that raced with the first cancellation may have observed the
            # brief no-operation gap and queued one more SYSTEM media.download;
            # once this commit is visible, no new automatic replacement may do so.
            download.automatic_retry_suppressed = (
                download.artifact_status != MediaDownloadArtifactStatus.AVAILABLE.value
            )
            payload = MediaDownloadAPIRead.model_validate(download)
            s.commit()
        except Exception:
            s.rollback()
            raise

    # Close the cancellation/requeue race without teaching the generic operation
    # controller about MediaDownload policy. Only a SYSTEM replacement can be the
    # automatic race described above; never cancel a new explicit UI/API retry
    # another caller may have started after the user's cancellation completed.
    with db_session() as s:
        replacement = get_active_media_download_operation(s, media_download_id)
        replacement_id = (
            replacement.id
            if replacement is not None and replacement.source == OperationSource.SYSTEM.value
            else None
        )

    if replacement_id is not None:
        try:
            cancel_operation(replacement_id, reason="Canceled by user", acknowledge=True)
        except ValueError:
            pass

    return payload


@router.get("/{media_download_id}/attempts", response_model=list[MediaDownloadAttemptAPIRead])
def media_downloads_attempts(media_download_id: int):
    with db_session() as s:
        return get_media_download_attempts(s, media_download_id)


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
    with db_session() as s:
        try:
            result = delete_media_download(s, media_download_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
