from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session() -> Session:
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_operation_does_not_adopt_run_with_cancellation_requested():
    from task_manager.scheduler.db import TaskDefinition, TaskOperationRun, TaskRun
    from task_manager.scheduler.operation_control import RUN_CANCEL_REQUESTED_META_KEY
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        operation_target_needs_dispatch,
    )
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus

    session = _session()
    try:
        definition = TaskDefinition(
            key="download_episode",
            title="Download episode",
            description=None,
            allowed_resource_types=["episode"],
            default_max_retries=0,
        )
        session.add(definition)
        session.flush()

        run = TaskRun(
            schedule_id=None,
            definition_id=definition.id,
            resource_type=ResourceType.EPISODE,
            resource_id=42,
            status=TaskStatus.RUNNING,
            progress=37,
            message="Downloading",
            meta={
                "inputs": {"profile_id": 7},
                RUN_CANCEL_REQUESTED_META_KEY: True,
            },
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

        operation = create_operation(
            session,
            kind="media.download.retry",
            resource_type="episode",
            resource_id=42,
            title="Retry download",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="episode",
                    resource_id=42,
                    task_kwargs={"profile_id": 7},
                    slot_key="episode:42",
                )
            ],
        )
        session.flush()

        assert operation.status == OperationStatus.QUEUED.value
        assert session.query(TaskOperationRun).count() == 0
        assert operation_target_needs_dispatch(session, operation.id, "episode:42") is True
    finally:
        session.close()
