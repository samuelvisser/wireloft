from __future__ import annotations

from sqlalchemy.orm import Session

from backend.api.endpoints.media_downloads.service import get_media_downloads_view
from backend.api.models.puller import FrontendPullAPIRead, FrontendPullData
from backend.types.download_profile_types import MediaDownloadStatus
from task_manager.scheduler.operations import list_operations
from task_manager.scheduler.types import OperationSource, OperationStatus


_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
}
_ACTIVE_DOWNLOAD_STATUSES = {
    MediaDownloadStatus.PENDING.value,
    MediaDownloadStatus.DOWNLOADING.value,
    MediaDownloadStatus.LOCAL_PROCESSING.value,
}


def _value(value) -> str:
    return str(getattr(value, "value", value))


def get_frontend_pull(s: Session) -> FrontendPullAPIRead:
    """Build the complete frontend polling snapshot in one HTTP request.

    Only UI-relevant operations are included, matching OperationNotifier's existing
    behavior. Downloads are returned as the same joined view used by the Downloads
    UI. The server chooses the next polling mode so the frontend does not need to
    know which status values count as active work.
    """
    operations = list_operations(
        source=OperationSource.UI.value,
        relevant=True,
        limit=200,
    )
    media_downloads = get_media_downloads_view(s)

    has_active_operation = any(
        _value(operation.get("status")) in _ACTIVE_OPERATION_STATUSES
        for operation in operations
    )
    has_active_download = any(
        _value(download.download_status) in _ACTIVE_DOWNLOAD_STATUSES
        for download in media_downloads
    )

    return FrontendPullAPIRead(
        mode="fast" if has_active_operation or has_active_download else "slow",
        data=FrontendPullData(
            operations=operations,
            media_downloads=media_downloads,
        ),
    )
