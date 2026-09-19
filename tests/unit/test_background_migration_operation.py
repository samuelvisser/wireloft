from __future__ import annotations


def test_background_migration_operation_is_created_once(task_database, monkeypatch):
    from task_manager.scheduler.db import TaskOperation
    from task_manager.tasks.workers.background_migration_runner import scheduling

    pending = [
        type("Migration", (), {"key": "first"})(),
        type("Migration", (), {"key": "second"})(),
    ]
    dispatched: list[tuple[str, str]] = []

    monkeypatch.setattr(
        scheduling,
        "get_current_background_migration_key",
        lambda: None,
    )
    monkeypatch.setattr(
        scheduling,
        "get_pending_background_migrations",
        lambda _current: tuple(pending),
    )
    monkeypatch.setattr(
        scheduling,
        "queue_operation_target_dispatch",
        lambda _session, operation_id, slot_key: dispatched.append(
            (operation_id, slot_key)
        ) or True,
    )

    first_id = scheduling.ensure_background_migration_operation()
    second_id = scheduling.ensure_background_migration_operation()

    assert first_id is not None
    assert second_id == first_id
    assert dispatched == [(first_id, "background-migrations")]

    with task_database() as session:
        operation = session.get(TaskOperation, first_id)
        assert operation is not None
        assert operation.kind == "system.background_migrations"
        assert operation.source == "SYSTEM"
        assert operation.resource_type == "system"
        assert operation.resource_id is None
        assert operation.context == {
            "target_key": "second",
            "migrations_pending": 2,
        }
        assert len(operation.targets) == 1
        assert operation.targets[0].task_key == "background_migration_runner"


def test_background_migration_operation_is_not_created_when_current(monkeypatch):
    from task_manager.tasks.workers.background_migration_runner import scheduling

    monkeypatch.setattr(
        scheduling,
        "get_current_background_migration_key",
        lambda: "current",
    )
    monkeypatch.setattr(
        scheduling,
        "get_pending_background_migrations",
        lambda _current: (),
    )

    assert scheduling.ensure_background_migration_operation() is None


def test_background_migration_runner_uses_critical_scheduler_lane():
    from task_manager.scheduler.registry import get_task
    from task_manager.tasks.workers.background_migration_runner.entrypoint import (
        background_migration_runner,
    )

    meta, worker = get_task("background_migration_runner")

    assert worker is background_migration_runner
    assert meta.pauses_scheduled_work is True
