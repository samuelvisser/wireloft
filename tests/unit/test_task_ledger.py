from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_task_ledger_filters_orders_and_paginates(monkeypatch):
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.tasks import service
    from backend.db import Base
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.db.TaskRun import TASK_RUN_WAIT_STATE_META_KEY
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
    definition_id = definition.id

    base = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    setup.add_all([
        TaskRun(
            definition_id=definition.id,
            schedule_id=None,
            resource_type=ResourceType.SHOW,
            resource_id=7,
            status=TaskStatus.SUCCEEDED,
            progress=100,
            message="before show creation",
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
            message="direct failure",
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
            resource_id=0,
            status=TaskStatus.SUCCEEDED,
            progress=100,
            message="global success",
            meta={"inputs": {}},
            result={
                "summary": "global",
                "data": {
                    "shows": [
                        {"show_id": 7, "show_slug": "show-seven", "episodes_found": 3},
                    ],
                },
            },
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=base + timedelta(minutes=2),
            finished_at=base + timedelta(minutes=2, seconds=1),
            runtime_ms=1000,
        ),
        TaskRun(
            definition_id=definition.id,
            schedule_id=None,
            resource_type=ResourceType.SHOW,
            resource_id=7,
            status=TaskStatus.RUNNING,
            progress=50,
            message="still running",
            meta={
                "inputs": {},
                TASK_RUN_WAIT_STATE_META_KEY: {
                    "reason": "daily_wire_request_cooldown",
                    "message": "Waiting for The Daily Wire request cooldown",
                    "until": base.timestamp() + 600,
                },
            },
            result=None,
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=base + timedelta(minutes=3),
            finished_at=None,
            runtime_ms=None,
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
            result={"summary": "other", "data": {"episodes_found": 4}},
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=base + timedelta(minutes=4),
            finished_at=base + timedelta(minutes=4, seconds=1),
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
            started_at=base + timedelta(minutes=5),
            finished_at=base + timedelta(minutes=5),
            runtime_ms=0,
        ),
    ])
    setup.commit()
    setup.close()

    monkeypatch.setattr(service, "get_session", lambda: Session(engine))

    first = service.list_ledger(
        definition_key="fetch_new_episodes",
        resource_type="show",
        resource_ids=[0, 7],
        statuses=[TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value],
        started_after=base + timedelta(seconds=30),
        order_by="started_at",
        order="desc",
        cursor=None,
        limit=1,
    )
    assert first.total == 2
    assert first.has_more is True
    assert first.next_cursor is not None
    assert [item.message for item in first.items] == ["global success"]
    assert first.items[0].result["data"]["shows"][0]["episodes_found"] == 3

    with pytest.raises(ValueError, match="Cursor does not match this task ledger"):
        service.list_ledger(
            definition_key="fetch_new_episodes",
            resource_type="show",
            resource_ids=[7],
            statuses=[TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value],
            started_after=base + timedelta(seconds=30),
            order_by="started_at",
            order="desc",
            cursor=first.next_cursor,
            limit=1,
        )

    # Mutate rows ahead of the cursor: remove the row page 1 ended on and add
    # a newer row. Neither change may shift the continuation boundary.
    with Session(engine) as mutation:
        mutation.delete(mutation.get(TaskRun, first.items[0].id))
        mutation.add(TaskRun(
            definition_id=definition_id,
            schedule_id=None,
            resource_type=ResourceType.SHOW,
            resource_id=7,
            status=TaskStatus.SUCCEEDED,
            progress=100,
            message="newer after page one",
            meta={"inputs": {}},
            result={"summary": "new"},
            attempt_count=1,
            max_retries=2,
            last_error=None,
            next_retry_at=None,
            started_at=base + timedelta(minutes=10),
            finished_at=base + timedelta(minutes=10, seconds=1),
            runtime_ms=1000,
        ))
        mutation.commit()

    second = service.list_ledger(
        definition_key="fetch_new_episodes",
        resource_type="show",
        resource_ids=[0, 7],
        statuses=[TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value],
        started_after=base + timedelta(seconds=30),
        order_by="started_at",
        order="desc",
        cursor=first.next_cursor,
        limit=1,
    )
    assert second.has_more is False
    assert [item.message for item in second.items] == ["direct failure"]
    assert second.items[0].last_error == "boom"
    assert second.items[0].inputs == {"show_slug": "show-seven"}

    waiting = service.list_ledger(
        definition_key="fetch_new_episodes",
        statuses=[TaskStatus.RUNNING.value],
        order_by="started_at",
        order="desc",
        cursor=None,
        limit=20,
    )
    assert waiting.total == 1
    assert waiting.items[0].wait_state is not None
    assert waiting.items[0].wait_state.reason == "daily_wire_request_cooldown"
    assert waiting.items[0].wait_state.message == "Waiting for The Daily Wire request cooldown"

    all_succeeded = service.list_ledger(
        definition_key=None,
        statuses=[TaskStatus.SUCCEEDED.value],
        order_by="started_at",
        order="desc",
        cursor=None,
        limit=20,
    )
    assert all_succeeded.total == 4
    assert all_succeeded.has_more is False
    assert all_succeeded.items[0].definition_key == "other_worker"
    assert all_succeeded.items[0].definition_title == "Other"
    assert all_succeeded.items[0].progress == 100
    assert all_succeeded.items[0].attempt_count == 1
    assert all_succeeded.items[0].created_at is not None

    engine.dispose()


def test_task_cursor_restarts_when_filtered_ordering_changes():
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.tasks.service import query_ledger
    from backend.db import Base
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        definition = TaskDefinition(
            key="revision_worker",
            title="Revision worker",
            description=None,
            allowed_resource_types=["show"],
            default_max_retries=0,
        )
        session.add(definition)
        session.flush()

        base = datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)
        runs = []
        for index in range(3):
            run = TaskRun(
                definition_id=definition.id,
                schedule_id=None,
                resource_type=ResourceType.SHOW,
                resource_id=1,
                status=TaskStatus.RUNNING,
                progress=index,
                message=f"run-{index}",
                meta={"inputs": {}},
                result=None,
                attempt_count=1,
                max_retries=0,
                last_error=None,
                next_retry_at=None,
                started_at=base + timedelta(minutes=index),
                finished_at=None,
                runtime_ms=None,
            )
            session.add(run)
            runs.append(run)
        session.commit()

        first = query_ledger(
            session,
            definition_key="revision_worker",
            statuses=[TaskStatus.RUNNING.value],
            order_by="started_at",
            order="desc",
            cursor=None,
            limit=1,
        )
        assert first.next_cursor is not None
        assert first.revision

        # This changes filtered membership and therefore invalidates the old
        # continuation boundary even though the cursor itself still decodes.
        runs[-1].status = TaskStatus.SUCCEEDED
        runs[-1].updated_at = base + timedelta(hours=1)
        session.commit()

        restarted = query_ledger(
            session,
            definition_key="revision_worker",
            statuses=[TaskStatus.RUNNING.value],
            order_by="started_at",
            order="desc",
            cursor=first.next_cursor,
            limit=1,
        )

        assert restarted.revision != first.revision
        assert [item.message for item in restarted.items] == ["run-1"]

    engine.dispose()
