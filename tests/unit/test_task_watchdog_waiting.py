from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_waiting_operation_keeps_linked_run_out_of_standalone_watchdog(task_database):
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.db.TaskRun import TASK_RUN_WAIT_STATE_META_KEY
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        refresh_operations_for_run,
    )
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus
    from task_manager.scheduler.watchdog import monitor_stalled_work, reset_watchdog_state

    reset_watchdog_state()
    session = task_database()
    definition = TaskDefinition(
        key="watchdog_wait_state_worker",
        title="Watchdog wait-state worker",
        description=None,
        allowed_resource_types=["show"],
        default_max_retries=0,
    )
    session.add(definition)
    session.flush()

    operation = create_operation(
        session,
        kind="show.sync",
        resource_type="show",
        resource_id=7,
        title="Waiting Show",
        targets=[
            OperationTargetSpec(
                task_key=definition.key,
                resource_type="show",
                resource_id=7,
            )
        ],
    )
    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.SHOW,
        resource_id=7,
        status=TaskStatus.RUNNING,
        progress=35,
        message="Working",
        meta={
            TASK_RUN_WAIT_STATE_META_KEY: {
                "reason": "daily_wire_request_cooldown",
                "message": "Waiting for Daily Wire request cooldown. Will resume soon.",
            }
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
    link_run_to_operations(
        session,
        run=run,
        task_key=definition.key,
        operation_ids=(operation.id,),
    )
    refresh_operations_for_run(session, run.id)
    operation_id = operation.id
    run_id = run.id
    assert operation.status == OperationStatus.WAITING.value
    session.commit()
    session.close()

    started = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    first = monitor_stalled_work(now=started, timeout_minutes=20)
    later = monitor_stalled_work(
        now=started + timedelta(minutes=40),
        timeout_minutes=20,
    )

    assert first.operations_canceled == 0
    assert first.task_runs_canceled == 0
    assert later.operations_canceled == 0
    assert later.task_runs_canceled == 0

    session = task_database()
    try:
        assert session.get(type(operation), operation_id).status == OperationStatus.WAITING.value
        assert session.get(TaskRun, run_id).status == TaskStatus.RUNNING
    finally:
        session.close()


def test_waiting_standalone_task_is_not_marked_stalled(task_database):
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.db.TaskRun import (
        TASK_RUN_PROGRESS_META_KEY,
        TASK_RUN_WAIT_STATE_META_KEY,
    )
    from task_manager.scheduler.types import ResourceType, TaskStatus
    from task_manager.scheduler.watchdog import monitor_stalled_work, reset_watchdog_state

    reset_watchdog_state()
    session = task_database()
    definition = TaskDefinition(
        key="standalone_wait_state_worker",
        title="Standalone wait-state worker",
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
        resource_id=8,
        status=TaskStatus.RUNNING,
        progress=None,
        message="Working",
        meta={
            TASK_RUN_WAIT_STATE_META_KEY: {
                "reason": "daily_wire_request_queue",
                "message": "Waiting for a turn to request The Daily Wire",
            },
            # Even stale structured activity must not turn an intentional wait
            # into a watchdog failure.
            TASK_RUN_PROGRESS_META_KEY: {
                "download": {
                    "heartbeat_at": 0,
                    "stages": [
                        {
                            "state": "running",
                            "phase": "transferring",
                            "started_at": 0,
                            "last_activity_at": 0,
                        }
                    ],
                }
            },
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
    session.commit()
    run_id = run.id
    session.close()

    started = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    first = monitor_stalled_work(now=started, timeout_minutes=20)
    later = monitor_stalled_work(
        now=started + timedelta(minutes=40),
        timeout_minutes=20,
    )

    assert first.task_runs_canceled == 0
    assert later.task_runs_canceled == 0

    session = task_database()
    try:
        persisted = session.get(TaskRun, run_id)
        assert persisted is not None
        assert persisted.status == TaskStatus.RUNNING
        assert persisted.wait_state is not None
        assert persisted.wait_state["reason"] == "daily_wire_request_queue"
    finally:
        session.close()
