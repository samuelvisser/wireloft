from __future__ import annotations

from config import get_settings

from backend.api.endpoints.operations.service import list_operations
from backend.api.models.puller import FrontendPullAPIRead, FrontendPullData
from task_manager.scheduler.types import OperationStatus


_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
}


def get_frontend_pull() -> FrontendPullAPIRead:
    """Return the frontend's generic changing-execution snapshot."""
    operations = list_operations(relevant=True, limit=500)

    # The frontend only calls /pull while its document is visible and focused.
    # Give it an opportunity to show a toast before sending a background push.
    from backend.services.push_notifications import record_foreground_poll
    record_foreground_poll()
    has_active_operation = any(
        operation.status in _ACTIVE_OPERATION_STATUSES
        for operation in operations
    )
    return FrontendPullAPIRead(
        app_version=get_settings().app_version,
        mode="fast" if has_active_operation else "slow",
        data=FrontendPullData(operations=operations),
    )
