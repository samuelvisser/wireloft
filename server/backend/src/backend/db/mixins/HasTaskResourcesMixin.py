from __future__ import annotations

import logging
from typing import ClassVar

from sqlalchemy import and_, event, select
from sqlalchemy.orm import Session, declared_attr, foreign, relationship

from task_manager.scheduler.types import ResourceType, TaskStatus


logger = logging.getLogger(__name__)
_PENDING_DELETED_RESOURCES_KEY = "wireloft.deleted_task_resources"
_PENDING_RELEASED_TASK_DEFINITIONS_KEY = "wireloft.released_task_definitions"


class HasTaskResourcesMixin:
    """Attach scheduler work to a domain resource through its generic resource key.

    The scheduler deliberately stores ``resource_type`` + ``resource_id`` instead
    of hard-coding one foreign key per domain model. These relationships give the
    generic key normal SQLAlchemy ownership semantics: deleting a resource also
    deletes its schedules, runs, operations and operation targets, while callers
    can navigate those collections directly from the resource model.
    """

    __task_resource_types__: ClassVar[tuple[str, ...]]

    @classmethod
    def _task_resource_values(cls) -> tuple[str, ...]:
        values = tuple(getattr(cls, "__task_resource_types__", ()))
        if not values:
            raise ValueError(
                f"{cls.__name__} uses HasTaskResourcesMixin without __task_resource_types__"
            )
        return values

    @classmethod
    def _task_resource_enums(cls) -> tuple[ResourceType, ...]:
        return tuple(ResourceType(value) for value in cls._task_resource_values())

    @declared_attr
    def task_schedules(cls):
        from task_manager.scheduler.db import TaskSchedule

        resource_types = cls._task_resource_enums()
        return relationship(
            TaskSchedule,
            primaryjoin=lambda: and_(
                foreign(TaskSchedule.resource_id) == cls.id,
                TaskSchedule.resource_type.in_(resource_types),
            ),
            cascade="all, delete",
            lazy="select",
            uselist=True,
            overlaps="task_schedules",
        )

    @declared_attr
    def task_runs(cls):
        from task_manager.scheduler.db import TaskRun

        resource_types = cls._task_resource_enums()
        return relationship(
            TaskRun,
            primaryjoin=lambda: and_(
                foreign(TaskRun.resource_id) == cls.id,
                TaskRun.resource_type.in_(resource_types),
            ),
            cascade="all, delete",
            lazy="select",
            uselist=True,
            overlaps="task_runs",
        )

    @declared_attr
    def task_operations(cls):
        from task_manager.scheduler.db import TaskOperation

        resource_types = cls._task_resource_values()
        return relationship(
            TaskOperation,
            primaryjoin=lambda: and_(
                foreign(TaskOperation.resource_id) == cls.id,
                TaskOperation.resource_type.in_(resource_types),
            ),
            cascade="all, delete",
            lazy="select",
            uselist=True,
            overlaps="task_operations",
        )

    @declared_attr
    def task_operation_targets(cls):
        from task_manager.scheduler.db import TaskOperationTarget

        resource_types = cls._task_resource_values()
        return relationship(
            TaskOperationTarget,
            primaryjoin=lambda: and_(
                foreign(TaskOperationTarget.resource_id) == cls.id,
                TaskOperationTarget.resource_type.in_(resource_types),
            ),
            cascade="all, delete",
            lazy="select",
            uselist=True,
            overlaps="task_operation_targets,targets",
        )


def _task_status(value) -> TaskStatus:
    return value if isinstance(value, TaskStatus) else TaskStatus(value)


def _run_released_task_callbacks(definition_ids: set[int]) -> None:
    """Refill constrained task queues when deletion removes a pending reservation."""
    if not definition_ids:
        return

    from backend.db.core import get_session
    from task_manager.scheduler.db import TaskDefinition
    from task_manager.scheduler.registry import get_task

    lookup = get_session()
    try:
        keys = lookup.scalars(
            select(TaskDefinition.key).where(TaskDefinition.id.in_(definition_ids))
        ).all()
    finally:
        lookup.close()

    callbacks = set()
    for key in keys:
        try:
            task_meta, _ = get_task(key)
        except KeyError:
            continue
        if task_meta.terminal_callback is not None:
            callbacks.add(task_meta.terminal_callback)

    for callback in callbacks:
        try:
            callback()
        except Exception:
            # The domain-resource deletion has already committed. A queue refill
            # failure must never make that successful deletion appear to fail.
            logger.exception("Failed to refill task queue after resource deletion")


@event.listens_for(Session, "after_flush")
def _remember_deleted_task_resources(session: Session, flush_context) -> None:
    from task_manager.scheduler.db import TaskRun

    resources: set[tuple[str, int]] = session.info.setdefault(
        _PENDING_DELETED_RESOURCES_KEY,
        set(),
    )
    released_definitions: set[int] = session.info.setdefault(
        _PENDING_RELEASED_TASK_DEFINITIONS_KEY,
        set(),
    )

    for item in session.deleted:
        # A pending/retry TaskRun occupied a durable queue slot but has no Python
        # worker still executing. Once its owning resource is deleted, a task
        # definition's generic terminal callback may immediately refill that slot.
        # RUNNING work is excluded: its executor invokes the callback only after
        # cooperative cancellation actually leaves the worker body.
        if isinstance(item, TaskRun):
            if _task_status(item.status) in {
                TaskStatus.SCHEDULED,
                TaskStatus.QUEUED,
                TaskStatus.RETRY_SCHEDULED,
            }:
                released_definitions.add(item.definition_id)

        if not isinstance(item, HasTaskResourcesMixin):
            continue
        resource_id = getattr(item, "id", None)
        if resource_id is None:
            continue
        for resource_type in item._task_resource_values():
            resources.add((resource_type, int(resource_id)))

    if not resources:
        session.info.pop(_PENDING_DELETED_RESOURCES_KEY, None)
    if not released_definitions:
        session.info.pop(_PENDING_RELEASED_TASK_DEFINITIONS_KEY, None)


@event.listens_for(Session, "after_commit")
def _remove_deleted_resource_jobs(session: Session) -> None:
    # A nested SAVEPOINT committed, but the outer transaction is still pending.
    if session.in_nested_transaction():
        return

    resources = session.info.pop(_PENDING_DELETED_RESOURCES_KEY, set())
    released_definitions = session.info.pop(
        _PENDING_RELEASED_TASK_DEFINITIONS_KEY,
        set(),
    )

    if resources:
        from task_manager.scheduler.scheduler import cancel_pending_resource_jobs

        cancel_pending_resource_jobs(resources)

    _run_released_task_callbacks(released_definitions)


@event.listens_for(Session, "after_rollback")
def _discard_deleted_resource_jobs(session: Session) -> None:
    session.info.pop(_PENDING_DELETED_RESOURCES_KEY, None)
    session.info.pop(_PENDING_RELEASED_TASK_DEFINITIONS_KEY, None)


@event.listens_for(Session, "after_soft_rollback")
def _discard_soft_rolled_back_resource_jobs(session: Session, previous_transaction) -> None:
    session.info.pop(_PENDING_DELETED_RESOURCES_KEY, None)
    session.info.pop(_PENDING_RELEASED_TASK_DEFINITIONS_KEY, None)
