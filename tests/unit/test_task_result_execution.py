from __future__ import annotations


def test_executor_persists_task_result_and_completes_operation(task_database):
    from task_manager.scheduler.db import TaskOperation, TaskRun
    from task_manager.scheduler.executor import execute_task
    from task_manager.scheduler.operations import OperationTargetSpec, create_operation
    from task_manager.scheduler.registry import sync_registry_to_db, task
    from task_manager.scheduler.results import TaskResult
    from task_manager.scheduler.types import OperationStatus, TaskStatus

    task_key = "test_structured_result_worker"

    @task(
        key=task_key,
        title="Structured result test",
        allowed_resource_types=("show",),
        default_max_retries=0,
        tracks_progress=True,
    )
    async def structured_result_worker(*, resource_id=None, progress=None):
        progress.set(60, "Found three episodes")
        return TaskResult(
            summary="Episode scan finished",
            data={"episodes_found": 3},
        )

    sync_registry_to_db()

    session = task_database()
    operation = create_operation(
        session,
        kind="test.structured_result",
        resource_type="show",
        resource_id=42,
        title="Test Show",
        targets=[
            OperationTargetSpec(
                task_key=task_key,
                resource_type="show",
                resource_id=42,
            )
        ],
    )
    operation_id = operation.id
    session.commit()
    session.close()

    execute_task(
        def_key=task_key,
        resource_type="show",
        resource_id=42,
        operation_ids=(operation_id,),
    )

    session = task_database()
    try:
        run = session.query(TaskRun).filter_by(resource_id=42).one()
        assert run.status == TaskStatus.SUCCEEDED
        assert run.progress == 100
        assert run.message == "Episode scan finished"
        assert run.result == {
            "summary": "Episode scan finished",
            "data": {"episodes_found": 3},
        }

        completed = session.get(TaskOperation, operation_id)
        assert completed is not None
        assert completed.status == OperationStatus.SUCCEEDED.value
        assert completed.progress == 100
        assert completed.result == run.result
    finally:
        session.close()
