from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


def _definition(session, key: str = "watchdog_worker"):
    from task_manager.scheduler.db import TaskDefinition

    definition = TaskDefinition(
        key=key,
        title="Watchdog worker",
        description=None,
        allowed_resource_types=["show"],
        default_max_retries=0,
    )
    session.add(definition)
    session.flush()
    return definition


def _running_task(session, definition, *, progress: int = 30):
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus

    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.SHOW,
        resource_id=7,
        status=TaskStatus.RUNNING,
        progress=progress,
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
    return run


def _running_operation(session, *, progress: int = 30):
    from task_manager.scheduler.db import TaskOperation
    from task_manager.scheduler.types import OperationSource, OperationStatus

    operation = TaskOperation(
        id="watchdog-operation",
        kind="show.sync",
        source=OperationSource.UI.value,
        resource_type="show",
        resource_id=7,
        title="Watchdog Show",
        status=OperationStatus.RUNNING.value,
        progress=progress,
        message="Working",
        result=None,
        context={},
        error=None,
        notification_seen_at=None,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
    )
    session.add(operation)
    session.flush()
    return operation


def test_watchdog_uses_reserved_executor(monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.watchdog import install_stalled_work_watchdog

    settings = SimpleNamespace(
        timezone="UTC",
        scheduler=SimpleNamespace(
            enabled=False,
            max_workers=3,
        ),
    )
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)

    scheduler = scheduler_module._new_scheduler()
    assert scheduler._executors["default"]._pool._max_workers == 3
    watchdog_executor = scheduler._executors[scheduler_module.WATCHDOG_EXECUTOR_ALIAS]
    assert watchdog_executor._pool._max_workers == 1

    captured: dict = {}

    class FakeScheduler:
        def add_job(self, *args, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(scheduler_module, "start_scheduler", lambda: FakeScheduler())
    install_stalled_work_watchdog()

    assert captured["executor"] == scheduler_module.WATCHDOG_EXECUTOR_ALIAS
    assert captured["max_instances"] == 1


def test_watchdog_cancels_only_after_progress_stays_unchanged(task_database, monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operation_control import RUN_CANCEL_REASON_META_KEY
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    from task_manager.scheduler.watchdog import monitor_stalled_work, reset_watchdog_state

    monkeypatch.setattr(scheduler_module, "cancel_pending_operation_jobs", lambda **kwargs: 0)
    monkeypatch.setattr(scheduler_module, "cancel_pending_task_run_jobs", lambda run_ids: 0)
    reset_watchdog_state()

    session = task_database()
    definition = _definition(session)
    task = _running_task(session, definition)
    operation = _running_operation(session)
    task_id = task.id
    operation_id = operation.id
    session.commit()
    session.close()

    started = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    first = monitor_stalled_work(now=started, timeout_minutes=20)
    assert first.operations_canceled == 0
    assert first.task_runs_canceled == 0

    almost = monitor_stalled_work(now=started + timedelta(minutes=19), timeout_minutes=20)
    assert almost.operations_canceled == 0
    assert almost.task_runs_canceled == 0

    # A percentage change resets the timeout independently for both layers.
    session = task_database()
    session.get(TaskRun, task_id).progress = 31
    session.get(TaskOperation, operation_id).progress = 31
    session.commit()
    session.close()

    changed_at = started + timedelta(minutes=19)
    changed = monitor_stalled_work(now=changed_at, timeout_minutes=20)
    assert changed.operations_canceled == 0
    assert changed.task_runs_canceled == 0

    stalled = monitor_stalled_work(
        now=changed_at + timedelta(minutes=20),
        timeout_minutes=20,
    )
    assert stalled.operations_canceled == 1
    assert stalled.task_runs_canceled == 1

    session = task_database()
    try:
        stored_operation = session.get(TaskOperation, operation_id)
        stored_task = session.get(TaskRun, task_id)
        assert stored_operation.status == OperationStatus.CANCELED.value
        assert stored_operation.notification_seen_at is None
        assert "20 minutes without progress" in stored_operation.message
        assert stored_task.status == TaskStatus.CANCELED
        assert stored_task.meta is not None
        assert "20 minutes without progress" in stored_task.meta[RUN_CANCEL_REASON_META_KEY]
    finally:
        session.close()


def test_watchdog_ignores_queue_time_and_starts_timeout_only_when_running(task_database, monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    from task_manager.scheduler.watchdog import monitor_stalled_work, reset_watchdog_state

    monkeypatch.setattr(scheduler_module, "cancel_pending_operation_jobs", lambda **kwargs: 0)
    monkeypatch.setattr(scheduler_module, "cancel_pending_task_run_jobs", lambda run_ids: 0)
    reset_watchdog_state()

    session = task_database()
    definition = _definition(session, "watchdog_waiting_worker")
    queued_task = _running_task(session, definition, progress=10)
    queued_task.status = TaskStatus.QUEUED
    scheduled_task = _running_task(session, definition, progress=20)
    scheduled_task.resource_id = 8
    scheduled_task.status = TaskStatus.SCHEDULED
    operation = _running_operation(session, progress=15)
    operation.status = OperationStatus.QUEUED.value
    queued_task_id = queued_task.id
    scheduled_task_id = scheduled_task.id
    operation_id = operation.id
    session.commit()
    session.close()

    waiting_since = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    monitor_stalled_work(now=waiting_since, timeout_minutes=20)
    still_waiting = monitor_stalled_work(
        now=waiting_since + timedelta(minutes=40),
        timeout_minutes=20,
    )
    assert still_waiting.operations_canceled == 0
    assert still_waiting.task_runs_canceled == 0

    session = task_database()
    assert session.get(TaskRun, queued_task_id).status == TaskStatus.QUEUED
    assert session.get(TaskRun, scheduled_task_id).status == TaskStatus.SCHEDULED
    assert session.get(TaskOperation, operation_id).status == OperationStatus.QUEUED.value
    session.get(TaskRun, queued_task_id).status = TaskStatus.RUNNING
    session.get(TaskRun, scheduled_task_id).status = TaskStatus.RUNNING
    session.get(TaskOperation, operation_id).status = OperationStatus.RUNNING.value
    session.commit()
    session.close()

    started = waiting_since + timedelta(minutes=40)
    first_running_observation = monitor_stalled_work(now=started, timeout_minutes=20)
    assert first_running_observation.operations_canceled == 0
    assert first_running_observation.task_runs_canceled == 0

    almost = monitor_stalled_work(now=started + timedelta(minutes=19), timeout_minutes=20)
    assert almost.operations_canceled == 0
    assert almost.task_runs_canceled == 0

    stalled = monitor_stalled_work(now=started + timedelta(minutes=20), timeout_minutes=20)
    assert stalled.operations_canceled == 1
    assert stalled.task_runs_canceled == 2


def test_watchdog_does_not_treat_retry_backoff_as_stalled_execution(task_database, monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus
    from task_manager.scheduler.watchdog import monitor_stalled_work, reset_watchdog_state

    monkeypatch.setattr(scheduler_module, "cancel_pending_task_run_jobs", lambda run_ids: 0)
    reset_watchdog_state()

    session = task_database()
    definition = _definition(session, "watchdog_retry_worker")
    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.SHOW,
        resource_id=8,
        status=TaskStatus.RETRY_SCHEDULED,
        progress=40,
        message="Retry scheduled",
        meta=None,
        result=None,
        attempt_count=1,
        max_retries=3,
        last_error="temporary",
        next_retry_at=datetime(2026, 9, 4, 13, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        finished_at=None,
        runtime_ms=None,
    )
    session.add(run)
    session.commit()
    run_id = run.id
    session.close()

    monitor_stalled_work(
        now=datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        timeout_minutes=20,
    )
    result = monitor_stalled_work(
        now=datetime(2026, 9, 4, 12, 40, tzinfo=timezone.utc),
        timeout_minutes=20,
    )
    assert result.task_runs_canceled == 0

    session = task_database()
    try:
        assert session.get(TaskRun, run_id).status == TaskStatus.RETRY_SCHEDULED
    finally:
        session.close()


def test_active_operation_owns_watchdog_for_its_task_run(task_database, monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, TaskStatus
    from task_manager.scheduler.watchdog import monitor_stalled_work, reset_watchdog_state

    monkeypatch.setattr(scheduler_module, "cancel_pending_operation_jobs", lambda **kwargs: 0)
    monkeypatch.setattr(scheduler_module, "cancel_pending_task_run_jobs", lambda run_ids: 0)
    reset_watchdog_state()

    session = task_database()
    definition = _definition(session, "watchdog_operation_owned_worker")
    operation = create_operation(
        session,
        kind="show.sync",
        resource_type="show",
        resource_id=7,
        title="Watchdog Show",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="show",
                resource_id=7,
            )
        ],
    )
    run = _running_task(session, definition, progress=30)
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(operation.id,),
    )
    refresh_operations_for_run(session, run.id)
    operation_id = operation.id
    run_id = run.id
    session.commit()
    session.close()

    started = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    monitor_stalled_work(now=started, timeout_minutes=20)

    # The operation itself makes progress at 19 minutes. The linked TaskRun's
    # own percentage remains unchanged, but it must not be killed independently:
    # the active operation owns the timeout semantics for shared/coalesced work.
    session = task_database()
    session.get(TaskOperation, operation_id).progress = 31
    session.commit()
    session.close()

    changed_at = started + timedelta(minutes=19)
    monitor_stalled_work(now=changed_at, timeout_minutes=20)
    result = monitor_stalled_work(
        now=started + timedelta(minutes=21),
        timeout_minutes=20,
    )
    assert result.operations_canceled == 0
    assert result.task_runs_canceled == 0

    session = task_database()
    try:
        assert session.get(TaskOperation, operation_id).status == OperationStatus.RUNNING.value
        assert session.get(TaskRun, run_id).status == TaskStatus.RUNNING
    finally:
        session.close()
