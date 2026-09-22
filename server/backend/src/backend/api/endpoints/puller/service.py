from __future__ import annotations

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
    has_active_operation = any(
        operation.status in _ACTIVE_OPERATION_STATUSES
        for operation in operations
    )
    return FrontendPullAPIRead(
        mode="fast" if has_active_operation else "slow",
        data=FrontendPullData(operations=operations),
    )
