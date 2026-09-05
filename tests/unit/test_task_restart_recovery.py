from __future__ import annotations


def test_restart_cancels_every_nonterminal_task_run(task_database):
    """In-memory scheduler work cannot survive a backend process restart."""
    import controller.app as controller_app
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus

    interrupted_statuses = (
        TaskStatus.SCHEDULED,
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.RETRY_SCHEDULED,
    )

    with task_database() as session:
        definition = TaskDefinition(
            key="restart-recovery-test",
            title="Restart recovery test",
            description=None,
            allowed_resource_types=["show"],
            default_max_retries=0,
        )
        session.add(definition)
        session.flush()

        runs = [
            TaskRun(
                definition_id=definition.id,
                resource_type=ResourceType.SHOW,
                resource_id=index + 1,
                status=status,
                progress=index * 10,
            )
            for index, status in enumerate(interrupted_statuses)
        ]
        session.add_all(runs)
        session.commit()
        run_ids = [run.id for run in runs]

    assert controller_app.clear_interrupted_task_runs() == len(interrupted_statuses)

    with task_database() as session:
        recovered = [session.get(TaskRun, run_id) for run_id in run_ids]
        assert all(run is not None for run in recovered)
        assert all(run.status == TaskStatus.CANCELED for run in recovered if run is not None)
        assert all(run.message == "Interrupted by WireLoft restart" for run in recovered if run is not None)
        assert all(run.finished_at is not None for run in recovered if run is not None)
