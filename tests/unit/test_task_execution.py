from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import select


def _install_task(monkeypatch, *, key: str, function, default_max_retries: int = 3):
    import task_manager.scheduler.registry as registry_module

    monkeypatch.setattr(registry_module, "_REGISTRY", {})
    decorated = registry_module.task(
        key=key,
        title="Original title",
        description="Original description",
        allowed_resource_types=("show",),
        default_max_retries=default_max_retries,
    )(function)
    registry_module.sync_registry_to_db()
    return decorated


def test_successful_task_persists_progress_and_terminal_state(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import execute_task

    async def worker(*, resource_id=None, progress=None, slug=None):
        progress.set(50, "Halfway")

    _install_task(monkeypatch, key="test_success", function=worker)
    execute_task(
        def_key="test_success",
        resource_type="show",
        resource_id=7,
        slug="stable-slug",
    )

    with task_database() as session:
        run = session.execute(select(TaskRun)).scalar_one()
        assert run.status == "SUCCEEDED"
        assert run.resource_id == 7
        assert run.progress == 100
        assert run.attempt_count == 1
        assert run.finished_at is not None
        assert run.next_retry_at is None
        assert run.meta == {"inputs": {"slug": "stable-slug"}}


def test_resource_type_is_forwarded_only_when_declared_and_never_persisted(task_database, monkeypatch):
    """Tasks that bind to more than one resource type (per-episode event vs. a
    global cron sweep, say) need to know which one a given run is for. That value
    is derived from the call, not a genuine input, so it must never leak into
    run.meta where a later retry would replay it as a stored input."""
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import execute_task

    seen = []

    async def worker(*, resource_id=None, progress=None, resource_type=None):
        seen.append(resource_type)

    _install_task(monkeypatch, key="test_resource_type", function=worker)
    execute_task(def_key="test_resource_type", resource_type="episode", resource_id=3)

    assert seen == ["episode"]
    with task_database() as session:
        run = session.execute(select(TaskRun)).scalar_one()
        assert run.meta is None


def test_resource_type_not_forwarded_when_undeclared(task_database, monkeypatch):
    from task_manager.scheduler.executor import execute_task

    async def worker(*, resource_id=None, progress=None):
        pass  # would raise TypeError if resource_type were forwarded

    _install_task(monkeypatch, key="test_no_resource_type", function=worker)
    execute_task(def_key="test_no_resource_type", resource_type="show", resource_id=1)


def test_zero_retry_override_is_terminal(task_database, monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import execute_task

    async def worker(*, resource_id=None, progress=None):
        raise RuntimeError("expected failure")

    _install_task(monkeypatch, key="test_no_retry", function=worker, default_max_retries=5)
    schedule_retry = Mock()
    monkeypatch.setattr(scheduler_module, "schedule_retry", schedule_retry)

    with pytest.raises(RuntimeError, match="expected failure"):
        execute_task(
            def_key="test_no_retry",
            resource_type="show",
            resource_id=1,
            max_retries=0,
        )

    schedule_retry.assert_not_called()
    with task_database() as session:
        run = session.execute(select(TaskRun)).scalar_one()
        assert run.status == "FAILED"
        assert run.max_retries == 0
        assert run.attempt_count == 1
        assert run.finished_at is not None
        assert run.next_retry_at is None


def test_retry_run_is_nonterminal_then_clears_retry_state_on_success(task_database, monkeypatch):
    import task_manager.scheduler.registry as registry_module
    import task_manager.scheduler.scheduler as scheduler_module
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import execute_task

    attempts = 0

    async def worker(*, resource_id=None, progress=None):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("retry me")

    _install_task(monkeypatch, key="test_retry", function=worker, default_max_retries=1)
    schedule_retry = Mock()
    monkeypatch.setattr(scheduler_module, "schedule_retry", schedule_retry)

    execute_task(def_key="test_retry", resource_type="show", resource_id=9)

    with task_database() as session:
        run = session.execute(select(TaskRun)).scalar_one()
        run_id = run.id
        assert run.status == "RETRY_SCHEDULED"
        assert run.attempt_count == 1
        assert run.next_retry_at is not None
        assert run.finished_at is None

    execute_task(
        def_key="test_retry",
        resource_type="show",
        resource_id=9,
        run_id=run_id,
    )

    with task_database() as session:
        run = session.get(TaskRun, run_id)
        assert run.status == "SUCCEEDED"
        assert run.attempt_count == 2
        assert run.next_retry_at is None
        assert run.finished_at is not None
        assert run.last_error is None
