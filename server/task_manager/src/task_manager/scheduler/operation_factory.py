from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy.orm import Session

from task_manager.scheduler.db import TaskOperation
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation as create_task_operation,
)
from task_manager.scheduler.types import OperationSource


ResourceT = TypeVar("ResourceT")


class OperationDefinition(Generic[ResourceT]):
    """Declarative description of one reusable high-level operation shape."""

    kind: ClassVar[str]
    resource_type: ClassVar[str]
    task: ClassVar[str | None] = None

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


class OperationFactory:
    """Materialize an OperationDefinition into scheduler state."""

    @staticmethod
    def create(
        session: Session,
        definition: OperationDefinition[Any],
    ) -> TaskOperation:
        return create_task_operation(
            session,
            kind=definition.kind,
            source=definition.source,
            resource_type=definition.resource_type,
            resource_id=definition.resource_id,
            title=definition.title,
            targets=tuple(definition.targets()),
            context=definition.context(),
        )


def create_operation(
    session: Session,
    definition: OperationDefinition[Any],
) -> TaskOperation:
    """Create an operation from its declarative definition."""
    return OperationFactory.create(session, definition)
