from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic_ns
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session() -> Session:
    import backend.db.models  # noqa: F401
    import task_manager.scheduler.db  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _reset_pacing_state(client) -> None:
    with client._pacing_condition:
        client._pacing_next_ticket = 0
        client._pacing_serving_ticket = 0
        client._last_request_ns = None
        client._ms_since_last_request = None
        client._fast_requests = 0
        client._pacing_condition.notify_all()


def test_dailywire_slow_cooldown_notifies_current_execution(monkeypatch):
    from dailywire_api.dw_api import client

    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: SimpleNamespace(
            dw_timeout=SimpleNamespace(
                min_fast_request_ms=0,
                max_fast_requests=0,
                min_slow_request_ms=20,
            )
        ),
    )

    _reset_pacing_state(client)
    try:
        with client._pacing_condition:
            client._last_request_ns = monotonic_ns()
            client._fast_requests = 0

        states: list[bool] = []
        with client.slow_request_cooldown_observer(states.append):
            client._wait_before_request()

        assert states == [True, False]
    finally:
        _reset_pacing_state(client)


def test_task_operation_reports_worker_wait_state():
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.operations import (
        TASK_RUN_WAIT_STATE_META_KEY,
        OperationTargetSpec,
        create_operation,
        refresh_operation,
    )
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus

    session = _session()
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

        operation = create_operation(
            session,
            kind="show.sync",
            resource_type="show",
            resource_id=42,
            title="Test Show",
            targets=[
                OperationTargetSpec(
                    task_key=definition.key,
                    resource_type="show",
                    resource_id=42,
                )
            ],
        )

        run.meta = {
            TASK_RUN_WAIT_STATE_META_KEY: {
                "reason": "daily_wire_request_cooldown",
                "message": "Waiting for Daily Wire request cooldown. Will resume soon.",
            }
        }
        session.flush()
        refresh_operation(session, operation.id)

        assert operation.status == OperationStatus.WAITING.value
        assert operation.progress == 35
        assert operation.message == "Waiting for Daily Wire request cooldown. Will resume soon."

        run.meta = None
        session.flush()
        refresh_operation(session, operation.id)

        assert operation.status == OperationStatus.RUNNING.value
        assert operation.progress == 35
        assert operation.message == "Working"
    finally:
        session.close()
