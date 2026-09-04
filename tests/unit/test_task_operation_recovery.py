from __future__ import annotations

from datetime import datetime, timezone


def test_interrupted_operation_detaches_dead_run_and_requeues_target(task_database, monkeypatch):
    from controller.app import clear_interrupted_task_runs
    from task_manager.scheduler.db import TaskDefinition, TaskOperation, TaskOperationRun, TaskRun
    from task_manager.scheduler.operations import (
        OperationTargetSpec,
        create_operation,
        link_run_to_operations,
        recover_pending_operations,
    )
    from task_manager.scheduler.registry import sync_registry_to_db, task
    from task_manager.scheduler.types import OperationStatus, ResourceType, TaskStatus
    import task_manager.scheduler.scheduler as scheduler_module

    task_key = "test_operation_recovery_worker"

    @task(
        key=task_key,
        title="Operation recovery test",
        allowed_resource_types=("episode",),
        default_max_retries=3,
    )
    async def recovery_worker(*, resource_id=None, refresh=False, progress=None):
        return None

    sync_registry_to_db()

    session = task_database()
    definition = session.query(TaskDefinition).filter_by(key=task_key).one()
    operation = create_operation(
        session,
        kind="episode.test_recovery",
        resource_type="episode",
        resource_id=17,
        title="Episode 17",
        targets=[
            OperationTargetSpec(
                task_key=task_key,
                resource_type="episode",
                resource_id=17,
                task_kwargs={"refresh": True},
                slot_key="episode:17",
            )
        ],
    )
    operation_id = operation.id

    run = TaskRun(
        schedule_id=None,
        definition_id=definition.id,
        resource_type=ResourceType.EPISODE,
        resource_id=17,
        status=TaskStatus.RETRY_SCHEDULED,
        progress=35,
        message="Retry scheduled",
        meta={"inputs": {"refresh": True}},
        result=None,
        attempt_count=1,
        max_retries=3,
        last_error="temporary failure",
        next_retry_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        runtime_ms=None,
    )
    session.add(run)
    session.flush()
    link_run_to_operations(
        session,
        run=run,
        task_key=task_key,
        operation_ids=(operation_id,),
        operation_slot="episode:17",
    )
    run_id = run.id
    session.commit()
    session.close()

    assert clear_interrupted_task_runs() == 1

    session = task_database()
    try:
        interrupted = session.get(TaskRun, run_id)
        assert interrupted is not None
        assert interrupted.status == TaskStatus.CANCELED
        assert interrupted.finished_at is not None
        assert interrupted.next_retry_at is None

        queued = session.get(TaskOperation, operation_id)
        assert queued is not None
        assert queued.status == OperationStatus.QUEUED.value
        assert session.query(TaskOperationRun).filter_by(task_run_id=run_id).count() == 0
    finally:
        session.close()

    dispatched: list[dict] = []
    monkeypatch.setattr(
        scheduler_module,
        "trigger_now",
        lambda **kwargs: dispatched.append(kwargs) or "job-id",
    )

    assert recover_pending_operations() == 1
    assert dispatched == [
        {
            "def_key": task_key,
            "resource_type": "episode",
            "resource_id": 17,
            "operation_ids": (operation_id,),
            "operation_slot": "episode:17",
            "refresh": True,
        }
    ]
