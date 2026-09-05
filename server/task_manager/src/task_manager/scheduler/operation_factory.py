from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy.orm import Session

from task_manager.events.transactional import queue_event
from task_manager.scheduler.db import TaskOperation
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    operation_target_needs_dispatch,
)
from task_manager.scheduler.types import OperationSource


ResourceT = TypeVar("ResourceT")


class OperationDefinition(Generic[ResourceT]):
    """Declarative description of one reusable high-level operation shape."""

    kind: ClassVar[str]
    resource_type: ClassVar[str]
    task: ClassVar[str | None] = None
    event: ClassVar[str | None] = None
    event_is_dispatch: ClassVar[bool] = False

    def __init__(
        self,
        resource: ResourceT,
        *,
        source: str = OperationSource.UI.value,
    ) -> None:
        self.resource = resource
        self.source = source

    @property
    def resource_id(self) -> int | None:
        return getattr(self.resource, "id", None)

    @property
    def title(self) -> str:
        title = getattr(self.resource, "title", None)
        if title:
            return str(title)
        if self.resource_id is not None:
            return f"{self.resource_type} {self.resource_id}"
        return self.kind

    def task_kwargs(self) -> dict[str, Any]:
        return {}

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        if self.task is None:
            return ()
        return (
            OperationTargetSpec(
                task_key=self.task,
                resource_type=self.resource_type,
                resource_id=self.resource_id,
                task_kwargs=self.task_kwargs(),
            ),
        )

    def context(self) -> dict[str, Any]:
        return {}

    def event_payload(self) -> dict[str, Any]:
        return {}


class OperationFactory:
    """Materialize an OperationDefinition into scheduler state and its declared event."""

    @staticmethod
    def create(
        session: Session,
        definition: OperationDefinition[Any],
    ) -> TaskOperation:
        targets = tuple(definition.targets())
        if definition.event_is_dispatch:
            if definition.event is None:
                raise ValueError(
                    f"{type(definition).__name__} marks its event as dispatch-only "
                    "but does not declare an event"
                )
            if len(targets) != 1:
                raise ValueError(
                    f"{type(definition).__name__} must define exactly one target "
                    "when its event is used for worker dispatch"
                )

        operation = create_operation(
            session,
            kind=definition.kind,
            source=definition.source,
            resource_type=definition.resource_type,
            resource_id=definition.resource_id,
            title=definition.title,
            targets=targets,
            context=definition.context(),
        )

        if definition.event is None:
            return operation

        if definition.event_is_dispatch:
            target = targets[0]
            if not operation_target_needs_dispatch(
                session,
                operation.id,
                target.resolved_slot_key(),
            ):
                return operation

        payload: dict[str, Any] = {}
        if definition.resource_id is not None:
            payload.update({
                "resource_id": definition.resource_id,
                "id": definition.resource_id,
            })
        payload.update(definition.event_payload())
        queue_event(session, definition.event, payload)
        return operation
