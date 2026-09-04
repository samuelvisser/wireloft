from __future__ import annotations

from datetime import datetime, timezone


def _definition(session, key: str):
    from task_manager.scheduler.db import TaskDefinition

    definition = TaskDefinition(
        key=key,
        title="Operation control test worker",
        description=None,
        allowed_resource_types=["episode"],
        default_max_retries=0,
    )
    session.add(definition)
    session.flush()
    return definition


def _run(session, definition, *, resource_id: int, status, progress: int, inputs: dict | None = None):
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.types import ResourceType

    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.EPISODE,
        resource_id=resource_id,
        status=status,
        progress=progress,
        message="Running",
        meta={"inputs": inputs} if inputs else None,
        result=None,
        attempt_count=1,
        max_retries=0,
        last_error=None,
        next_retry_at=None,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc) if str(status).endswith("SUCCEEDED") else None,
        runtime_ms=None,
    )
    session.add(run)
    session.flush()
    return run


def test_cancel_operation_is_durable_and_requests_running_worker_stop(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import (
        RUN_CANCEL_REQUESTED_META_KEY,
        cancel_operation,
    )
    from task_manager.scheduler.operations import (
        WORKER_PROGRESS_META_KEY,
        OperationTargetSpec,
        create_operation,
        get_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_cancel_operation_worker")
    operation = create_operation(
        session,
        kind="episode.test_cancel",
        resource_type="episode",
        resource_id=17,
        title="Episode 17",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=17,
            )
        ],
    )
    operation_id = operation.id
    run = _run(
        session,
        definition,
        resource_id=17,
        status=TaskStatus.RUNNING,
        progress=42,
    )
    run.meta = {WORKER_PROGRESS_META_KEY: True}
    run_id = run.id
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(operation_id,),
    )
    refresh_operations_for_run(session, run_id)
    session.commit()
    session.close()

    canceled_jobs: list[tuple[str, set[int]]] = []
    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda *, operation_id, run_ids=(): canceled_jobs.append((operation_id, set(run_ids))) or 0,
    )

    payload = cancel_operation(operation_id)
    assert payload is not None
    assert payload["status"] == OperationStatus.CANCELED.value
    assert payload["progress"] == 42
    assert canceled_jobs == [(operation_id, {run_id})]

    # Refreshing the operation must not resurrect it from linked RUNNING state.
    refreshed = get_operation(operation_id)
    assert refreshed is not None
    assert refreshed["status"] == OperationStatus.CANCELED.value

    session = task_database()
    try:
        stored_operation = session.get(TaskOperation, operation_id)
        stored_run = session.get(TaskRun, run_id)
        assert stored_operation is not None
        assert stored_operation.finished_at is not None
        assert stored_run is not None
        assert stored_run.meta is not None
        assert stored_run.meta[RUN_CANCEL_REQUESTED_META_KEY] is True
    finally:
        session.close()


def test_cancel_operation_does_not_stop_run_shared_with_another_active_operation(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import (
        RUN_CANCEL_REQUESTED_META_KEY,
        cancel_operation,
    )
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_shared_cancel_worker")
    target = OperationTargetSpec(
        task_key=definition.key,
        resource_type="episode",
        resource_id=23,
    )
    first = create_operation(
        session,
        kind="episode.test_cancel.first",
        resource_type="episode",
        resource_id=23,
        title="First request",
        targets=[target],
    )
    second = create_operation(
        session,
        kind="episode.test_cancel.second",
        resource_type="episode",
        resource_id=23,
        title="Second request",
        targets=[target],
    )
    first_id = first.id
    second_id = second.id
    run = _run(
        session,
        definition,
        resource_id=23,
        status=TaskStatus.RUNNING,
        progress=31,
    )
    run_id = run.id
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(first_id, second_id),
    )
    refresh_operations_for_run(session, run_id)
    session.commit()
    session.close()

    canceled_jobs: list[tuple[str, set[int]]] = []
    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda *, operation_id, run_ids=(): canceled_jobs.append((operation_id, set(run_ids))) or 0,
    )

    payload = cancel_operation(first_id)
    assert payload is not None
    assert payload["status"] == OperationStatus.CANCELED.value
    assert canceled_jobs == [(first_id, set())]

    session = task_database()
    try:
        shared_run = session.get(TaskRun, run_id)
        assert shared_run is not None
        assert shared_run.status == TaskStatus.RUNNING
        assert not isinstance(shared_run.meta, dict) or RUN_CANCEL_REQUESTED_META_KEY not in shared_run.meta
        still_active = session.get(TaskOperation, second_id)
        assert still_active is not None
        assert still_active.status == OperationStatus.RUNNING.value
    finally:
        session.close()


def test_restart_operation_keeps_completed_targets_and_requeues_only_unfinished(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperationRun, TaskRun
    from task_manager.scheduler.operation_control import (
        RUN_CANCEL_REQUESTED_META_KEY,
        restart_operation,
    )
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    import task_manager.scheduler.scheduler as scheduler_module

    session = task_database()
    definition = _definition(session, "test_restart_operation_worker")
    operation = create_operation(
        session,
        kind="show.test_restart",
        resource_type="show",
        resource_id=5,
        title="Test Show",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=101,
                slot_key="episode:101",
            ),
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="episode",
                resource_id=102,
                slot_key="episode:102",
            ),
        ],
    )
    operation_id = operation.id

    completed_run = _run(
        session,
        definition,
        resource_id=101,
        status=TaskStatus.SUCCEEDED,
        progress=100,
    )
    completed_run_id = completed_run.id
    running_run = _run(
        session,
        definition,
        resource_id=102,
        status=TaskStatus.RUNNING,
        progress=37,
    )
    running_run_id = running_run.id

    link_run_to_operations(
        session,
        run=completed_run,
        task_key=definition.key,
        operation_ids=(operation_id,),
        operation_slot="episode:101",
    )
    link_run_to_operations(
        session,
        run=running_run,
        task_key=definition.key,
        operation_ids=(operation_id,),
        operation_slot="episode:102",
    )
    refresh_operations_for_run(session, completed_run_id)
    refresh_operations_for_run(session, running_run_id)
    session.commit()
    session.close()

    canceled_jobs: list[tuple[str, set[int]]] = []
    dispatched: list[dict] = []
    monkeypatch.setattr(
        scheduler_module,
        "cancel_pending_operation_jobs",
        lambda *, operation_id, run_ids=(): canceled_jobs.append((operation_id, set(run_ids))) or 0,
    )
    monkeypatch.setattr(
        scheduler_module,
        "trigger_now",
        lambda **kwargs: dispatched.append(kwargs) or "job-id",
    )

    payload = restart_operation(operation_id)
    assert payload is not None
    assert payload["status"] in {OperationStatus.QUEUED.value, OperationStatus.RUNNING.value}
    assert payload["progress"] == 50
    assert canceled_jobs == [(operation_id, {running_run_id})]
    assert dispatched == [
        {
            "def_key": definition.key,
            "resource_type": "episode",
            "resource_id": 102,
            "operation_ids": (operation_id,),
            "operation_slot": "episode:102",
        }
    ]

    session = task_database()
    try:
        running = session.get(TaskRun, running_run_id)
        assert running is not None
        assert running.meta is not None
        assert running.meta[RUN_CANCEL_REQUESTED_META_KEY] is True

        links = session.query(TaskOperationRun).filter_by(operation_id=operation_id).all()
        assert len(links) == 1
        assert links[0].task_run_id == completed_run_id
    finally:
        session.close()


def test_executor_skips_retry_run_after_cancellation_request(task_database):
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.executor import execute_task
    from task_manager.scheduler.operation_control import RUN_CANCEL_REQUESTED_META_KEY
    from task_manager.scheduler.registry import sync_registry_to_db, task
    from task_manager.scheduler.types import ResourceType, TaskStatus

    calls: list[int | None] = []
    task_key = "test_canceled_retry_worker"

    @task(
        key=task_key,
        title="Canceled retry worker",
        allowed_resource_types=("episode",),
        default_max_retries=0,
    )
    async def canceled_retry_worker(*, resource_id=None, progress=None):
        calls.append(resource_id)

    sync_registry_to_db()

    session = task_database()
    definition = session.query(TaskDefinition).filter_by(key=task_key).one()
    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.EPISODE,
        resource_id=55,
        status=TaskStatus.RETRY_SCHEDULED,
        progress=20,
        message="Retry scheduled",
        meta={RUN_CANCEL_REQUESTED_META_KEY: True},
        result=None,
        attempt_count=1,
        max_retries=1,
        last_error="temporary failure",
        next_retry_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        runtime_ms=None,
    )
    session.add(run)
    session.commit()
    run_id = run.id
    session.close()

    execute_task(
        def_key=task_key,
        resource_type="episode",
        resource_id=55,
        run_id=run_id,
    )

    assert calls == []
    session = task_database()
    try:
        canceled = session.get(TaskRun, run_id)
        assert canceled is not None
        assert canceled.status == TaskStatus.CANCELED
        assert canceled.finished_at is not None
    finally:
        session.close()
