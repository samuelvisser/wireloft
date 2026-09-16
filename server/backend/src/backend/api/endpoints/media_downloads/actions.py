from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.models.media_download import MediaDownloadAPIRead
from backend.app import db_session
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import queue_operation_target_dispatch
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
)

from .operations import _BulkMediaDownloadOperation
from .service import delete_media_download, retry_media_download


def retry_media_download_action(
        media_download_id: int,
        *,
        source: str = OperationSource.UI.value,
        reuse_matching_active: bool = False,
) -> str:
    """Replace one download attempt and return the new media.download operation ID."""
    active_operation_id: str | None = None
    is_redownload = False
    with db_session() as s:
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            raise HTTPException(status_code=404, detail="Media download not found")
        active = get_active_media_download_operation(s, media_download_id)
        if active is not None:
            if reuse_matching_active and active.source == source:
                return active.id
            active_operation_id = active.id
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
                source=source,
                is_redownload=is_redownload,
            )
            dispatch_queued_media_download_operations(s)
            operation_id = operation.id
            s.commit()
            return operation_id
        except Exception:
            s.rollback()
            raise


def cancel_media_download_action(
        media_download_id: int,
        *,
        allow_inactive: bool = False,
        missing_ok: bool = False,
) -> MediaDownloadAPIRead | None:
    """Cancel one download and durably suppress automatic replacement work."""
    operation_id: str | None = None
    with db_session() as s:
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            if missing_ok:
                return None
            raise HTTPException(status_code=404, detail="Media download not found")
        operation = get_active_media_download_operation(s, media_download_id)
        if operation is None:
            if not allow_inactive:
                raise HTTPException(status_code=409, detail="This download is not currently in progress")
        else:
            operation_id = operation.id

    if operation_id is not None:
        try:
            cancel_operation(operation_id, reason="Canceled by user", acknowledge=True)
        except ValueError as exc:
            if not allow_inactive:
                raise HTTPException(status_code=409, detail="This download is not currently in progress") from exc

    with db_session() as s:
        try:
            download = s.get(MediaDownloadBase, media_download_id)
            if download is None:
                if missing_ok:
                    return None
                raise HTTPException(status_code=404, detail="Media download not found")

            # Persist the user's intent even when an earlier bulk attempt already
            # canceled the active worker but crashed before recording suppression.
            download.automatic_retry_suppressed = (
                download.artifact_status != MediaDownloadArtifactStatus.AVAILABLE.value
            )
            payload = MediaDownloadAPIRead.model_validate(download)
            s.commit()
        except Exception:
            s.rollback()
            raise

    # Close the cancellation/requeue race without canceling a newer explicit retry.
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


def delete_media_download_action(
        media_download_id: int,
        *,
        missing_ok: bool = False,
) -> MediaDownloadAPIRead | None:
    """Delete one download record using the ordinary domain deletion path."""
    with db_session() as s:
        try:
            if missing_ok and s.get(MediaDownloadBase, media_download_id) is None:
                return None
            result = delete_media_download(s, media_download_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


def queue_bulk_media_download_operation(
        s: Session,
        operation: _BulkMediaDownloadOperation,
) -> dict[str, bool | int | str]:
    """Validate selected rows, create one operation, and dispatch its row targets."""
    ids = operation.media_download_ids
    if not ids:
        raise HTTPException(status_code=422, detail="At least one media download is required")

    existing_ids = set(s.scalars(
        select(MediaDownloadBase.id).where(MediaDownloadBase.id.in_(ids))
    ))
    missing_ids = [media_download_id for media_download_id in ids if media_download_id not in existing_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Media download {missing_ids[0]} not found",
        )

    queued_operation = create_operation(s, operation)
    for media_download_id in ids:
        queue_operation_target_dispatch(
            s,
            queued_operation.id,
            f"media_download:{media_download_id}",
        )

    return {
        "queued": True,
        "downloads_queued": len(ids),
        "operation_id": queued_operation.id,
    }
