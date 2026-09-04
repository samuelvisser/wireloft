"""Queue scheduler work until the surrounding SQLAlchemy transaction commits."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)
_PENDING_DISPATCHES_KEY = "wireloft.pending_task_dispatches"


@dataclass(frozen=True)
class PendingTaskDispatch:
    def_key: str
    resource_type: str
    resource_id: int | None
    operation_ids: tuple[str, ...]
    operation_slot: str | None
    kwargs: dict[str, Any]


def queue_task_after_commit(
        session: Session,
        *,
        def_key: str,
        resource_type: str,
        resource_id: int | None,
        operation_ids: tuple[str, ...] = (),
        operation_slot: str | None = None,
        **kwargs: Any,
) -> None:
    """Schedule a task only after the transaction that requested it commits."""
    dispatch = PendingTaskDispatch(
        def_key=def_key,
        resource_type=resource_type,
        resource_id=resource_id,
        operation_ids=tuple(operation_ids),
        operation_slot=operation_slot,
        kwargs=dict(kwargs),
    )
    pending: list[PendingTaskDispatch] = session.info.setdefault(_PENDING_DISPATCHES_KEY, [])
    if dispatch not in pending:
        pending.append(dispatch)


@event.listens_for(Session, "after_commit")
def _dispatch_committed_tasks(session: Session) -> None:
    # A nested SAVEPOINT committed, but the outer transaction is still pending.
    if session.in_nested_transaction():
        return

    pending: list[PendingTaskDispatch] = session.info.pop(_PENDING_DISPATCHES_KEY, [])
    if not pending:
        return

    from task_manager.scheduler.scheduler import trigger_now

    for item in pending:
        try:
            trigger_now(
                def_key=item.def_key,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                operation_ids=item.operation_ids,
                operation_slot=item.operation_slot,
                **item.kwargs,
            )
        except Exception:
            # The database commit has already succeeded. Keep dispatch failures
            # observable; durable TaskOperation targets can be recovered on restart.
            logger.exception(
                "Failed to dispatch committed task %s for %s:%s",
                item.def_key,
                item.resource_type,
                item.resource_id,
            )


@event.listens_for(Session, "after_rollback")
def _discard_rolled_back_tasks(session: Session) -> None:
    session.info.pop(_PENDING_DISPATCHES_KEY, None)


@event.listens_for(Session, "after_soft_rollback")
def _discard_soft_rolled_back_tasks(session: Session, previous_transaction) -> None:
    session.info.pop(_PENDING_DISPATCHES_KEY, None)
