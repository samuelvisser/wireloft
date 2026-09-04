from __future__ import annotations


def _install_task(monkeypatch, *, key: str, function):
    import task_manager.scheduler.registry as registry_module

    monkeypatch.setattr(registry_module, "_REGISTRY", {})
    registry_module.task(
        key=key,
        title="Connection lifecycle worker",
        allowed_resource_types=("show",),
        default_max_retries=0,
    )(function)
    registry_module.sync_registry_to_db()


def test_executor_releases_tracking_connection_before_worker_runs(task_database, monkeypatch):
    from backend.db import core
    from task_manager.scheduler.executor import execute_task

    checked_out: list[int] = []

    async def worker(*, resource_id=None, progress=None):
        checked_out.append(core._engine.pool.checkedout())

    _install_task(monkeypatch, key="test_executor_connection_release", function=worker)

    execute_task(
        def_key="test_executor_connection_release",
        resource_type="show",
        resource_id=11,
    )

    assert checked_out == [0]


def test_missing_retry_run_is_not_recreated_after_resource_cleanup(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import execute_task

    calls: list[int | None] = []

    async def worker(*, resource_id=None, progress=None):
        calls.append(resource_id)

    _install_task(monkeypatch, key="test_deleted_retry_run", function=worker)

    execute_task(
        def_key="test_deleted_retry_run",
        resource_type="show",
        resource_id=12,
    )

    session = task_database()
    run = session.query(TaskRun).one()
    run_id = run.id
    session.delete(run)
    session.commit()
    session.close()

    execute_task(
        def_key="test_deleted_retry_run",
        resource_type="show",
        resource_id=12,
        run_id=run_id,
    )

    assert calls == [12]
    session = task_database()
    try:
        assert session.query(TaskRun).count() == 0
    finally:
        session.close()
