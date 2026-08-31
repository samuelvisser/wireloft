from __future__ import annotations

from unittest.mock import Mock


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    def add_job(self, function, **kwargs):
        self.jobs[kwargs["id"]] = {"function": function, **kwargs}


def test_event_trigger_is_idempotent_and_preserves_supported_payload(monkeypatch):
    import task_manager.scheduler.executor as executor_module
    import task_manager.scheduler.registry as registry_module
    import task_manager.scheduler.scheduler as scheduler_module
    from controller.app import setup_triggers_from_registry
    from task_manager.events.emitters import emit_event
    from task_manager.events.registry import WireloftEventLinker, wait_for_events

    monkeypatch.setattr(registry_module, "_REGISTRY", {})

    @registry_module.on_event("test.entity.changed", resource_type="show")
    @registry_module.task(
        key="test_event_target",
        title="Test event target",
        allowed_resource_types=("show",),
    )
    async def target(*, resource_id=None, slug=None, show_id=None, manual_request_id=None, progress=None):
        return None

    trigger_now = Mock()
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(executor_module, "trigger_now", trigger_now)
    monkeypatch.setattr(scheduler_module, "start_scheduler", lambda: fake_scheduler)

    setup_triggers_from_registry()
    setup_triggers_from_registry()
    assert WireloftEventLinker.get_subscriber_count_from_event("test.entity.changed") == 1

    emit_event("test.entity.changed", {
        "resource_id": 0,
        "id": 99,
        "slug": "stable-slug",
        "show_id": 7,
        "manual_request_id": "manual-sync-123",
        "ignored": "not accepted by the worker",
    })
    wait_for_events()

    trigger_now.assert_called_once_with(
        def_key="test_event_target",
        resource_type="show",
        resource_id=0,
        slug="stable-slug",
        show_id=7,
        manual_request_id="manual-sync-123",
    )
