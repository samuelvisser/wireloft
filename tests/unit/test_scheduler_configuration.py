from __future__ import annotations

from types import SimpleNamespace


def test_scheduler_uses_configured_worker_limit(monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module

    settings = SimpleNamespace(
        timezone="UTC",
        scheduler=SimpleNamespace(
            enabled=False,
            max_workers=3,
        ),
    )
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)

    scheduler = scheduler_module._new_scheduler()
    executor = scheduler._executors["default"]
    assert executor._pool._max_workers == 3


def test_immediate_operation_jobs_do_not_expire_while_waiting_for_worker(monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module

    captured: dict = {}

    class FakeScheduler:
        timezone = __import__("datetime").timezone.utc

        def add_job(self, *args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="job-id")

    monkeypatch.setattr(scheduler_module, "start_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(
        "task_manager.scheduler.operation_context.current_operation_ids",
        lambda: (),
    )

    job_id = scheduler_module.trigger_now(
        def_key="worker",
        resource_type="show",
        resource_id=1,
        operation_ids=("operation-id",),
    )

    assert job_id == "job-id"
    assert captured["misfire_grace_time"] is None
    assert captured["kwargs"]["operation_ids"] == ("operation-id",)


def test_scheduler_disabled_keeps_task_execution_available(monkeypatch):
    import task_manager.scheduler.scheduler as scheduler_module

    settings = SimpleNamespace(
        timezone="UTC",
        scheduler=SimpleNamespace(
            enabled=False,
            max_workers=2,
        ),
    )
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    monkeypatch.setattr(scheduler_module, "_critical_scheduler", None)

    scheduler = scheduler_module.start_scheduler()
    try:
        assert scheduler.running
    finally:
        scheduler_module.shutdown_scheduler(wait=False)


def test_scheduled_work_pause_is_reference_counted(monkeypatch):
    import task_manager.scheduler.registry as registry_module
    import task_manager.scheduler.scheduler as scheduler_module

    settings = SimpleNamespace(
        timezone="UTC",
        scheduler=SimpleNamespace(
            enabled=True,
            max_workers=2,
        ),
    )
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)
    monkeypatch.setattr(registry_module, "_REGISTRY", {})

    @registry_module.task(
        key="critical_test_worker",
        title="Critical test worker",
        allowed_resource_types=("system",),
        pauses_scheduled_work=True,
    )
    async def critical_test_worker(*, resource_id=None, progress=None):
        return None

    @registry_module.task(
        key="normal_test_worker",
        title="Normal test worker",
        allowed_resource_types=("show",),
    )
    async def normal_test_worker(*, resource_id=None, progress=None):
        return None

    scheduler_module.shutdown_scheduler(wait=False)
    normal_scheduler = scheduler_module.start_scheduler()
    critical_scheduler = scheduler_module._critical_scheduler

    try:
        assert critical_scheduler is not None
        assert scheduler_module._scheduler_for_task("normal_test_worker") is normal_scheduler
        assert scheduler_module._scheduler_for_task("critical_test_worker") is critical_scheduler

        first = scheduler_module.pause_scheduled_work("first")
        second = scheduler_module.pause_scheduled_work("second")

        assert scheduler_module.scheduled_work_is_paused()
        assert normal_scheduler.state == scheduler_module.STATE_PAUSED
        assert critical_scheduler.running
        assert critical_scheduler.state != scheduler_module.STATE_PAUSED

        first.release()
        assert scheduler_module.scheduled_work_is_paused()
        assert normal_scheduler.state == scheduler_module.STATE_PAUSED

        second.release()
        assert not scheduler_module.scheduled_work_is_paused()
        assert normal_scheduler.running
        assert normal_scheduler.state != scheduler_module.STATE_PAUSED
    finally:
        scheduler_module.shutdown_scheduler(wait=False)


def test_critical_dispatch_holds_pause_before_job_runs(monkeypatch):
    import task_manager.scheduler.registry as registry_module
    import task_manager.scheduler.scheduler as scheduler_module

    captured: dict = {}

    class FakeScheduler:
        timezone = __import__("datetime").timezone.utc

        def add_job(self, *args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="critical-job")

    class FakePause:
        token = "pause-token"

        def release(self):
            captured["released"] = True

    monkeypatch.setattr(registry_module, "_REGISTRY", {})

    @registry_module.task(
        key="critical_dispatch_worker",
        title="Critical dispatch",
        allowed_resource_types=("system",),
        pauses_scheduled_work=True,
    )
    async def critical_dispatch_worker(*, resource_id=None, progress=None):
        return None

    monkeypatch.setattr(
        scheduler_module,
        "_scheduler_for_task",
        lambda _def_key: FakeScheduler(),
    )
    monkeypatch.setattr(
        scheduler_module,
        "pause_scheduled_work",
        lambda _reason: FakePause(),
    )
    monkeypatch.setattr(
        "task_manager.scheduler.operation_context.current_operation_ids",
        lambda: (),
    )

    job_id = scheduler_module.trigger_now(
        def_key="critical_dispatch_worker",
        resource_type="system",
        resource_id=None,
    )

    assert job_id == "critical-job"
    assert captured["kwargs"]["_scheduled_work_pause_token"] == "pause-token"
    assert "released" not in captured
