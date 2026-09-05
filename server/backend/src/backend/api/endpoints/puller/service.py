from __future__ import annotations

from backend.api.models.puller import FrontendPullAPIRead, FrontendPullData
from task_manager.scheduler.operations import list_operations
from task_manager.scheduler.types import OperationStatus


_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
}


def _value(value) -> str:
    return str(getattr(value, "value", value))


def get_frontend_pull() -> FrontendPullAPIRead:
    """Return the frontend's one generic stream of changing execution state.

    Active operations from every source are visible. Terminal operations remain
    visible until a frontend has processed them, even when they were started by
    automation or an API client. This guarantees completion-driven cache refreshes
    cannot be missed merely because a short operation began and ended between two
    slow polls. OperationNotifier decides which sources deserve a user-facing toast.
    """
    operations = list_operations(relevant=True, limit=500)
    has_active_operation = any(
        _value(operation.get("status")) in _ACTIVE_OPERATION_STATUSES
        for operation in operations
    )

    return FrontendPullAPIRead(
        mode="fast" if has_active_operation else "slow",
        data=FrontendPullData(operations=operations),
    )
