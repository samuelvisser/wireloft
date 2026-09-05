from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_task_ledger_filters_orders_and_paginates(monkeypatch):
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.tasks import service
    from backend.db import Base
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    setup = Session(engine)
    definition = TaskDefinition(
        key="fetch_new_episodes",
        title="Fetch episodes",
        description=None,
        allowed_resource_types=["show"],
        default_max_retries=2,
    )
    other_definition = TaskDefinition(
        key="other_worker",
        title="Other",
        description=None,
        allowed_resource_types=["show"],
        default_max_retries=0,
    )
    setup.add_all([definition, other_definition])
    setup.flush()

    base = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    setup.add_all([
        TaskRun(
            definition_id=definition.id,
            schedule_id=None,
            resource_type=ResourceType.SHOW,
            resource_id=7,
            status=TaskStatus.SUCCEEDED,
            progress=100,
            message="old",
            meta={"inputs": {"show_slug": "show-seven"}},
            result={"summary": "old", "data": {"episodes_found": 1}},
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=base,
            finished_at=base + timedelta(seconds=1),
            runtime_ms=1000,
        ),
        TaskRun(
            definition_id=definition.id,
            schedule_id=None,
            resource_type=ResourceType.SHOW,
            resource_id=7,
            status=TaskStatus.FAILED,
            progress=None,
            message="new",
            meta={"inputs": {"show_slug": "show-seven"}},
            result=None,
            attempt_count=1,
            max_retries=2,
            last_error="boom",
            next_retry_at=None,
            started_at=base + timedelta(minutes=1),
            finished_at=base + timedelta(minutes=1, seconds=2),
            runtime_ms=2000,
        ),
        TaskRun(
            definition_id=definition.id,
            schedule_id=None,
            resource_type=ResourceType.SHOW,
            resource_id=8,
            status=TaskStatus.SUCCEEDED,
            progress=100,
            message="other resource",
            meta={"inputs": {}},
            result={"summary": "other", "data": {"episodes_found": 3}},
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=base + timedelta(minutes=2),
            finished_at=base + timedelta(minutes=2, seconds=1),
            runtime_ms=1000,
        ),
        TaskRun(
            definition_id=other_definition.id,
            schedule_id=None,
            resource_type=ResourceType.SHOW,
            resource_id=7,
            status=TaskStatus.SUCCEEDED,
            progress=100,
            message="wrong task",
            meta={"inputs": {}},
            result=None,
            attempt_count=1,
            max_retries=0,
            last_error=None,
            next_retry_at=None,
            started_at=base + timedelta(minutes=3),
            finished_at=base + timedelta(minutes=3),
            runtime_ms=0,
        ),
    ])
    setup.commit()
    setup.close()

    monkeypatch.setattr(service, "get_session", lambda: Session(engine))

    first = service.list_ledger(
        definition_key="fetch_new_episodes",
        resource_type="show",
        resource_id=7,
        order_by="started_at",
        order="desc",
        offset=0,
        limit=1,
    )
    assert first["total"] == 2
    assert first["has_more"] is True
    assert [item["message"] for item in first["items"]] == ["new"]
    assert first["items"][0]["last_error"] == "boom"
    assert first["items"][0]["inputs"] == {"show_slug": "show-seven"}

    second = service.list_ledger(
        definition_key="fetch_new_episodes",
        resource_type="show",
        resource_id=7,
        order_by="started_at",
        order="desc",
        offset=1,
        limit=1,
    )
    assert second["has_more"] is False
    assert [item["message"] for item in second["items"]] == ["old"]
    assert second["items"][0]["result"]["data"]["episodes_found"] == 1

    engine.dispose()
