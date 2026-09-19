from __future__ import annotations

from sqlalchemy import select

from backend.db.background_migrations import (
    get_current_background_migration_key,
    get_pending_background_migrations,
)
from backend.db.core import get_session
from task_manager.scheduler.db import TaskOperation
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    queue_operation_target_dispatch,
)
from task_manager.scheduler.types import OperationSource, OperationStatus


BACKGROUND_MIGRATION_OPERATION_KIND = "system.background_migrations"
BACKGROUND_MIGRATION_TASK_KEY = "background_migration_runner"
_BACKGROUND_MIGRATION_SLOT = "background-migrations"
_ACTIVE_OPERATION_STATUSES = (
    OperationStatus.QUEUED.value,
    OperationStatus.RUNNING.value,
    OperationStatus.WAITING.value,
)


def ensure_background_migration_operation() -> str | None:
    """Create one system operation when the Settings key is behind code history."""

    current = get_current_background_migration_key()
    pending = get_pending_background_migrations(current)
    if not pending:
        return None

    session = get_session()
    try:
        existing = session.scalar(
            select(TaskOperation)
            .where(
                TaskOperation.kind == BACKGROUND_MIGRATION_OPERATION_KIND,
                TaskOperation.status.in_(_ACTIVE_OPERATION_STATUSES),
            )
            .order_by(TaskOperation.created_at.desc())
        )
        if existing is not None:
            return existing.id

        operation = create_operation(
            session,
            kind=BACKGROUND_MIGRATION_OPERATION_KIND,
            source=OperationSource.SYSTEM.value,
            resource_type="system",
            resource_id=None,
            title="Background migrations",
            targets=(
                OperationTargetSpec(
                    task_key=BACKGROUND_MIGRATION_TASK_KEY,
                    resource_type="system",
                    resource_id=None,
                    slot_key=_BACKGROUND_MIGRATION_SLOT,
                ),
            ),
            context={
                "target_key": pending[-1].key,
                "migrations_pending": len(pending),
            },
        )
        queue_operation_target_dispatch(
            session,
            operation.id,
            _BACKGROUND_MIGRATION_SLOT,
        )
        operation_id = operation.id
        session.commit()
        return operation_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
