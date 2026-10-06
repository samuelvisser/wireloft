from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.models.media_download import MediaDownloadAPIRead
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.services import download_actions as actions
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import queue_operation_target_dispatch
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.media_download_operations import attach_redownload_dependencies
from .operations import _BulkMediaDownloadOperation


def _invoke(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except actions.DownloadActionError as exc:
        raise HTTPException(status_code=404 if exc.kind == "missing" else 409, detail=str(exc)) from exc


def retry_media_download_action(
        media_download_id: int,
        *,
        source: str = OperationSource.UI,
        reuse_matching_active: bool = False,
        redownload_when_delay_passed: bool = False,
) -> str:
    return _invoke(
        actions.retry_media_download_action,
        media_download_id,
        source=source,
        reuse_matching_active=reuse_matching_active,
        redownload_when_delay_passed=redownload_when_delay_passed,
    )


def cancel_media_download_action(media_download_id: int, *, allow_inactive: bool = False, missing_ok: bool = False) -> MediaDownloadAPIRead | None:
    download = _invoke(actions.cancel_media_download_action, media_download_id, allow_inactive=allow_inactive, missing_ok=missing_ok)
    return MediaDownloadAPIRead.model_validate(download) if download is not None else None


def delete_media_download_artifact_action(media_download_id: int, *, missing_ok: bool = False) -> bool:
    return _invoke(actions.delete_media_download_artifact_action, media_download_id, missing_ok=missing_ok)


def delete_unavailable_media_download_action(media_download_id: int, *, missing_ok: bool = False) -> bool:
    return _invoke(actions.delete_unavailable_media_download_action, media_download_id, missing_ok=missing_ok)


def queue_bulk_media_download_operation(
        s: Session,
        operation: _BulkMediaDownloadOperation,
) -> dict[str, bool | int | str]:
    """Validate selected rows, create one operation, and dispatch its row targets."""
    ids = operation.media_download_ids
    if not ids:
        raise HTTPException(status_code=422, detail="At least one media download is required")

    downloads = list(s.scalars(
        select(MediaDownloadBase)
        .where(MediaDownloadBase.id.in_(ids))
        .order_by(MediaDownloadBase.id.asc())
    ))
    downloads_by_id = {download.id: download for download in downloads}
    missing_ids = [media_download_id for media_download_id in ids if media_download_id not in downloads_by_id]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Media download {missing_ids[0]} not found",
        )

    if operation.action == "delete_unavailable":
        non_deletable_ids = [
            media_download_id
            for media_download_id in ids
            if downloads_by_id[media_download_id].artifact_status
            not in {
                MediaDownloadArtifactStatus.ABSENT.value,
                MediaDownloadArtifactStatus.MISSING.value,
            }
        ]
        if non_deletable_ids:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Media download {non_deletable_ids[0]} has an available "
                    "or corrupted artifact and cannot be deleted"
                ),
            )

    queued_operation = create_operation(s, operation)
    if operation.action == "retry":
        attach_redownload_dependencies(
            s,
            queued_operation,
            tuple(downloads_by_id[download_id] for download_id in ids),
        )
    else:
        for target in queued_operation.targets:
            queue_operation_target_dispatch(
                s,
                queued_operation.id,
                target.slot_key,
            )

    return {
        "queued": True,
        "downloads_queued": len(ids),
        "operation_id": queued_operation.id,
    }
