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
