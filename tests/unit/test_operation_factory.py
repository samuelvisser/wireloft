from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@dataclass
class _Resource:
    id: int
    title: str
    slug: str


def _session() -> tuple[Session, Engine]:
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def test_factory_creates_operation_target_context_and_domain_event():
    from task_manager.scheduler.operation_factory import OperationDefinition, OperationFactory

    class IndexOperation(OperationDefinition[_Resource]):
        kind = "show.index"
        resource_type = "show"
        task = "test_worker"
        event = "show.added"

        def context(self) -> dict[str, str]:
            return {"show_slug": self.resource.slug}

        def event_payload(self) -> dict[str, str]:
            return {"slug": self.resource.slug}

    session, engine = _session()
    try:
        operation = OperationFactory.create(
            session,
            IndexOperation(_Resource(id=42, title="Test Show", slug="test-show")),
        )

        assert operation.kind == "show.index"
        assert operation.resource_type == "show"
        assert operation.resource_id == 42
        assert operation.title == "Test Show"
        assert operation.context == {"show_slug": "test-show"}
        assert len(operation.targets) == 1
        assert operation.targets[0].task_key == "test_worker"
        assert operation.targets[0].resource_type == "show"
        assert operation.targets[0].resource_id == 42

        pending = session.info["wireloft.pending_events"]
        assert len(pending) == 1
        assert pending[0].name == "show.added"
        assert pending[0].data == {
            "resource_id": 42,
            "id": 42,
            "slug": "test-show",
        }
    finally:
        session.close()
        engine.dispose()


def test_dispatch_event_is_queued_when_target_needs_work():
    from task_manager.scheduler.operation_factory import OperationDefinition, OperationFactory

    class SyncOperation(OperationDefinition[_Resource]):
        kind = "show.sync"
        resource_type = "show"
        task = "test_worker"
        event = "show.sync_requested"
        event_is_dispatch = True

        def event_payload(self) -> dict[str, str]:
            return {"slug": self.resource.slug}

    session, engine = _session()
    try:
        OperationFactory.create(
            session,
            SyncOperation(_Resource(id=42, title="Test Show", slug="test-show")),
        )

        pending = session.info["wireloft.pending_events"]
        assert len(pending) == 1
        assert pending[0].name == "show.sync_requested"
        assert pending[0].data == {
            "resource_id": 42,
            "id": 42,
            "slug": "test-show",
        }
    finally:
        session.close()
        engine.dispose()


def test_dispatch_event_is_skipped_when_compatible_work_is_already_running():
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.operation_factory import OperationDefinition, OperationFactory
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus

    class SyncOperation(OperationDefinition[_Resource]):
        kind = "show.sync"
        resource_type = "show"
        task = "test_worker"
        event = "show.sync_requested"
        event_is_dispatch = True

    session, engine = _session()
    try:
        definition = TaskDefinition(
            key="test_worker",
            title="Test worker",
            description=None,
            allowed_resource_types=["show"],
            default_max_retries=0,
        )
        session.add(definition)
        session.flush()

        run = TaskRun(
            schedule_id=None,
            definition_id=definition.id,
            resource_type=ResourceType.SHOW,
            resource_id=42,
            status=TaskStatus.RUNNING,
            progress=35,
            message="Working",
            meta=None,
            result=None,
            attempt_count=1,
            max_retries=0,
            last_error=None,
            next_retry_at=None,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            runtime_ms=None,
        )
        session.add(run)
        session.flush()

        operation = OperationFactory.create(
            session,
            SyncOperation(_Resource(id=42, title="Test Show", slug="test-show")),
        )

        assert operation.status == OperationStatus.RUNNING.value
        assert operation.progress == 35
        assert session.info.get("wireloft.pending_events", []) == []
    finally:
        session.close()
        engine.dispose()
