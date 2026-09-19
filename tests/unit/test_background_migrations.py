from __future__ import annotations

import asyncio

import pytest


def _migration(key: str, upstream_key: str | None):
    from backend.db.background_migrations.registry import BackgroundMigration

    return BackgroundMigration(
        key=key,
        upstream_key=upstream_key,
        title=key,
        migrate=lambda _context: None,
        module_name=f"test.{key}",
    )


def test_background_migration_chain_is_ordered_by_upstream_key():
    from backend.db.background_migrations.registry import _validate_migration_chain

    ordered = _validate_migration_chain(
        [
            _migration("third", "second"),
            _migration("first", None),
            _migration("second", "first"),
        ]
    )

    assert [migration.key for migration in ordered] == ["first", "second", "third"]


def test_background_migration_chain_rejects_branches():
    from backend.db.background_migrations.registry import (
        BackgroundMigrationError,
        _validate_migration_chain,
    )

    with pytest.raises(BackgroundMigrationError, match="multiple successors"):
        _validate_migration_chain(
            [
                _migration("first", None),
                _migration("second", "first"),
                _migration("alternate", "first"),
            ]
        )


def test_episode_indexing_is_one_registered_background_migration():
    from backend.db.background_migrations.registry import (
        get_background_migration_history,
    )

    history = get_background_migration_history()

    assert [(migration.key, migration.upstream_key) for migration in history] == [
        ("episode_indexing_semantics", None),
    ]


def test_background_migration_runner_uses_stored_key_as_source_of_truth(monkeypatch):
    from backend.db.background_migrations import runner

    calls: list[str] = []
    advances: list[tuple[str | None, str]] = []

    async def migrate_second(_context):
        calls.append("second")

    async def migrate_third(_context):
        calls.append("third")

    second = runner.BackgroundMigration(
        key="second",
        upstream_key="first",
        title="Second",
        migrate=migrate_second,
        module_name="test.second",
    )
    third = runner.BackgroundMigration(
        key="third",
        upstream_key="second",
        title="Third",
        migrate=migrate_third,
        module_name="test.third",
    )

    monkeypatch.setattr(runner, "get_background_migration_head_key", lambda: "third")
    monkeypatch.setattr(runner, "get_current_background_migration_key", lambda: "first")
    monkeypatch.setattr(
        runner,
        "get_pending_background_migrations",
        lambda current: (second, third) if current == "first" else (),
    )
    monkeypatch.setattr(
        runner,
        "advance_background_migration_version",
        lambda *, expected_key, new_key: advances.append((expected_key, new_key)),
    )

    result = asyncio.run(runner.run_pending_background_migrations())

    assert calls == ["second", "third"]
    assert advances == [("first", "second"), ("second", "third")]
    assert result.current_key == "third"
    assert result.applied_keys == ("second", "third")


def test_background_migration_runner_returns_when_already_current(monkeypatch):
    from backend.db.background_migrations import runner

    monkeypatch.setattr(runner, "get_background_migration_head_key", lambda: "current")
    monkeypatch.setattr(runner, "get_current_background_migration_key", lambda: "current")

    result = asyncio.run(runner.run_pending_background_migrations())

    assert result.current_key == "current"
    assert result.applied_keys == ()
