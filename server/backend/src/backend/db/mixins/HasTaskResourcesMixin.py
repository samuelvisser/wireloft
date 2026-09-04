from __future__ import annotations

from typing import ClassVar

from sqlalchemy import and_, event
from sqlalchemy.orm import Session, declared_attr, foreign, relationship

from task_manager.scheduler.types import ResourceType


_PENDING_DELETED_RESOURCES_KEY = "wireloft.deleted_task_resources"


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


@event.listens_for(Session, "after_flush")
def _remember_deleted_task_resources(session: Session, flush_context) -> None:
    resources: set[tuple[str, int]] = session.info.setdefault(
        _PENDING_DELETED_RESOURCES_KEY,
        set(),
    )
    for item in session.deleted:
        if not isinstance(item, HasTaskResourcesMixin):
            continue
        resource_id = getattr(item, "id", None)
        if resource_id is None:
            continue
        for resource_type in item._task_resource_values():
            resources.add((resource_type, int(resource_id)))
    if not resources:
        session.info.pop(_PENDING_DELETED_RESOURCES_KEY, None)


@event.listens_for(Session, "after_commit")
def _remove_deleted_resource_jobs(session: Session) -> None:
    # A nested SAVEPOINT committed, but the outer transaction is still pending.
    if session.in_nested_transaction():
        return

    resources = session.info.pop(_PENDING_DELETED_RESOURCES_KEY, set())
    if not resources:
        return

    from task_manager.scheduler.scheduler import cancel_pending_resource_jobs

    cancel_pending_resource_jobs(resources)


@event.listens_for(Session, "after_rollback")
def _discard_deleted_resource_jobs(session: Session) -> None:
    session.info.pop(_PENDING_DELETED_RESOURCES_KEY, None)


@event.listens_for(Session, "after_soft_rollback")
def _discard_soft_rolled_back_resource_jobs(session: Session, previous_transaction) -> None:
    session.info.pop(_PENDING_DELETED_RESOURCES_KEY, None)
