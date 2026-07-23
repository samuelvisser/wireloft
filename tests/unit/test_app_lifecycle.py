from __future__ import annotations

import asyncio
import threading
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
