from __future__ import annotations

from backend.api.models.puller import FrontendPullAPIRead, FrontendPullData
from task_manager.scheduler.operations import list_operations
from task_manager.scheduler.types import OperationSource, OperationStatus


_ACTIVE_OPERATION_STATUSES = {
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
}


def _value(value) -> str:
    return str(getattr(value, "value", value))


def get_frontend_pull() -> FrontendPullAPIRead:
    """Return the frontend's one generic stream of changing execution state.

    Active operations from every source are visible, so work started by schedules,
    API clients or another browser is discovered by the same pipeline. Completed
    non-UI operations are intentionally omitted: they need no user notification
    and their domain results are ordinary query data. UI operations remain until
    OperationNotifier acknowledges their terminal notification.
    """
    candidates = list_operations(relevant=True, limit=500)
    operations = [
        operation
        for operation in candidates
        if _value(operation.get("status")) in _ACTIVE_OPERATION_STATUSES
        or _value(operation.get("source")) == OperationSource.UI.value
    ]
    has_active_operation = any(
        _value(operation.get("status")) in _ACTIVE_OPERATION_STATUSES
        for operation in operations
    )

    return FrontendPullAPIRead(
        mode="fast" if has_active_operation else "slow",
        data=FrontendPullData(operations=operations),
    )
