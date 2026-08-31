from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from unittest.mock import Mock


def test_app_factory_is_side_effect_free_and_lifespan_owns_controller(monkeypatch):
    import controller
    from backend.app import create_app

    start = Mock()
    stop = Mock()
    monkeypatch.setattr(controller, "start_controller", start)
    monkeypatch.setattr(controller, "stop_controller", stop)

    first_app = create_app()
    assert start.call_count == 0
    assert stop.call_count == 0

    async def run_lifespan(app, expected_start_count, expected_stop_count):
        async with app.router.lifespan_context(app):
            assert start.call_count == expected_start_count
            assert stop.call_count == expected_stop_count

    asyncio.run(run_lifespan(first_app, 1, 0))
    assert stop.call_count == 1

    second_app = create_app()
    asyncio.run(run_lifespan(second_app, 2, 1))
    assert start.call_count == 2
    assert stop.call_count == 2


def test_controller_uses_asgi_loop_and_resets_scheduler(task_database, monkeypatch):
    import controller.app as controller_app
    import task_manager.scheduler.scheduler as scheduler_module

    monkeypatch.setattr(controller_app, "_controller_started", False)
    monkeypatch.setattr(controller_app, "emit_startup_event", lambda: None)

    async def run_controller():
        controller_app.start_controller()
        try:
            scheduler = scheduler_module._scheduler
            assert scheduler is not None
            assert scheduler.running
            assert scheduler._eventloop is asyncio.get_running_loop()
            assert scheduler_module._loop_thread is None
        finally:
            controller_app.stop_controller()

    asyncio.run(run_controller())

    assert scheduler_module._scheduler is None
    assert scheduler_module._loop is None
    assert scheduler_module._loop_thread is None
    assert not any(thread.name.startswith("wireloft") for thread in threading.enumerate())


def test_controller_cancels_task_runs_interrupted_by_restart(task_database, monkeypatch):
    import controller.app as controller_app
    from task_manager.scheduler.db import TaskDefinition, TaskRun
    from task_manager.scheduler.types import ResourceType, TaskStatus

    with task_database() as session:
        definition = TaskDefinition(
            key="legacy-indexing-task",
            title="Legacy indexing task",
            description=None,
            allowed_resource_types=["show"],
            default_max_retries=0,
        )
        session.add(definition)
        session.flush()

        interrupted = TaskRun(
            definition_id=definition.id,
            resource_type=ResourceType.SHOW,
            resource_id=42,
            status=TaskStatus.RUNNING,
            progress=65,
            started_at=datetime.now(timezone.utc),
        )
        completed = TaskRun(
            definition_id=definition.id,
            resource_type=ResourceType.SHOW,
            resource_id=43,
            status=TaskStatus.SUCCEEDED,
            progress=100,
            message="OK",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        session.add_all([interrupted, completed])
        session.commit()
        interrupted_id = interrupted.id
        completed_id = completed.id

    monkeypatch.setattr(controller_app, "_controller_started", False)
    monkeypatch.setattr(controller_app, "emit_startup_event", lambda: None)

    async def run_controller():
        controller_app.start_controller()
        try:
            with task_database() as session:
                interrupted = session.get(TaskRun, interrupted_id)
                completed = session.get(TaskRun, completed_id)

                assert interrupted is not None
                assert interrupted.status == TaskStatus.CANCELED
                assert interrupted.message == "Interrupted by WireLoft restart"
                assert interrupted.finished_at is not None
                # Preserve the last recorded percentage as historical context;
                # it is no longer considered active once the status is canceled.
                assert interrupted.progress == 65

                assert completed is not None
                assert completed.status == TaskStatus.SUCCEEDED
                assert completed.message == "OK"
        finally:
            controller_app.stop_controller()

    asyncio.run(run_controller())
