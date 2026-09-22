from __future__ import annotations

import asyncio
from types import ModuleType

import pytest


def _migration(revision: str, down_revision: str | None):
    from backend.db.background_migrations.registry import BackgroundMigration

    return BackgroundMigration(
        revision=revision,
        down_revision=down_revision,
        title=revision,
        migrate=lambda _context: None,
        module_name=f"test.{revision}_migration",
    )


def test_background_migration_chain_is_ordered_by_down_revision():
    from backend.db.background_migrations.registry import _validate_migration_chain

    first = "111111111111"
    second = "222222222222"
    third = "333333333333"
    ordered = _validate_migration_chain(
        [
            _migration(third, second),
            _migration(first, None),
            _migration(second, first),
        ]
    )

    assert [migration.revision for migration in ordered] == [first, second, third]


def test_background_migration_chain_rejects_branches():
    from backend.db.background_migrations.registry import (
        BackgroundMigrationError,
        _validate_migration_chain,
    )

    first = "111111111111"
    with pytest.raises(BackgroundMigrationError, match="multiple successors"):
        _validate_migration_chain(
            [
                _migration(first, None),
                _migration("222222222222", first),
                _migration("333333333333", first),
            ]
        )


def test_background_migration_revision_must_be_alembic_style():
    from backend.db.background_migrations.registry import (
        BackgroundMigrationError,
        _migration_from_module,
    )

    module = ModuleType(
        "backend.db.background_migrations.versions.episode_indexing_semantics"
    )
    module.revision = "episode_indexing_semantics"
    module.down_revision = None
    module.migrate = lambda _context: None

    with pytest.raises(
        BackgroundMigrationError,
        match="12-character lowercase hexadecimal revision",
    ):
        _migration_from_module(module)


def test_background_migration_filename_must_start_with_revision():
    from backend.db.background_migrations.registry import (
        BackgroundMigrationError,
        _migration_from_module,
    )

    module = ModuleType("backend.db.background_migrations.versions.wrong_name")
    module.revision = "111111111111"
    module.down_revision = None
    module.migrate = lambda _context: None

    with pytest.raises(
        BackgroundMigrationError,
        match="111111111111_<description>",
    ):
        _migration_from_module(module)


def test_unknown_stored_background_revision_reports_history_mismatch(monkeypatch):
    from backend.db.background_migrations import registry

    first = "111111111111"
    head = "222222222222"
    unknown = "aaaaaaaaaaaa"
    history = (
        _migration(first, None),
        _migration(head, first),
    )
    monkeypatch.setattr(
        registry,
        "get_background_migration_history",
        lambda: history,
    )

    with pytest.raises(
        registry.UnknownBackgroundMigrationRevisionError
    ) as exc_info:
        registry.get_pending_background_migrations(unknown)

    error = exc_info.value
    assert error.current_revision == unknown
    assert error.known_revisions == (first, head)
    assert error.head_revision == head

    message = str(error)
    assert f"Database is at background migration revision {unknown!r}" in message
    assert "does not contain that revision" in message
    assert f"Known revisions: {first!r}, {head!r}" in message
    assert f"Latest known revision: {head!r}" in message
    assert "newer or different WireLoft build" in message
    assert "squashed without preserving its latest applied revision" in message


def test_episode_indexing_background_migration_history_is_linear():
    from backend.db.background_migrations.registry import (
        get_background_migration_history,
    )

    history = get_background_migration_history()

    assert [
        (migration.revision, migration.down_revision)
        for migration in history
    ] == [
        ("f6a1c3d8b427", None),
        ("9d4b7e2c1a63", "f6a1c3d8b427"),
        ("3c8f6a1d2b47", "9d4b7e2c1a63"),
    ]
    assert history[0].module_name.endswith(
        ".f6a1c3d8b427_episode_indexing_semantics"
    )
    assert history[1].module_name.endswith(
        ".9d4b7e2c1a63_restore_high_segment_auxiliary"
    )
    assert history[2].module_name.endswith(
        ".3c8f6a1d2b47_square_show_thumbnails"
    )


def test_background_migration_runner_uses_stored_revision_as_source_of_truth(monkeypatch):
    from backend.db.background_migrations import runner

    calls: list[str] = []
    advances: list[tuple[str | None, str]] = []

    first = "111111111111"
    second_revision = "222222222222"
    third_revision = "333333333333"

    async def migrate_second(_context):
        calls.append("second")

    async def migrate_third(_context):
        calls.append("third")

    second = runner.BackgroundMigration(
        revision=second_revision,
        down_revision=first,
        title="Second",
        migrate=migrate_second,
        module_name=f"test.{second_revision}_second",
    )
    third = runner.BackgroundMigration(
        revision=third_revision,
        down_revision=second_revision,
        title="Third",
        migrate=migrate_third,
        module_name=f"test.{third_revision}_third",
    )

    monkeypatch.setattr(
        runner,
        "get_background_migration_head_revision",
        lambda: third_revision,
    )
    monkeypatch.setattr(
        runner,
        "get_current_background_migration_revision",
        lambda: first,
    )
    monkeypatch.setattr(
        runner,
        "get_pending_background_migrations",
        lambda current: (second, third) if current == first else (),
    )
    monkeypatch.setattr(
        runner,
        "advance_background_migration_revision",
        lambda *, expected_revision, new_revision: advances.append(
            (expected_revision, new_revision)
        ),
    )

    result = asyncio.run(runner.run_pending_background_migrations())

    assert calls == ["second", "third"]
    assert advances == [
        (first, second_revision),
        (second_revision, third_revision),
    ]
    assert result.current_revision == third_revision
    assert result.applied_revisions == (second_revision, third_revision)


def test_background_migration_runner_returns_when_already_current(monkeypatch):
    from backend.db.background_migrations import runner

    current = "111111111111"
    monkeypatch.setattr(
        runner,
        "get_background_migration_head_revision",
        lambda: current,
    )
    monkeypatch.setattr(
        runner,
        "get_current_background_migration_revision",
        lambda: current,
    )

    result = asyncio.run(runner.run_pending_background_migrations())

    assert result.current_revision == current
    assert result.applied_revisions == ()


def test_backend_run_validates_background_migration_state_before_uvicorn(
    monkeypatch,
    capsys,
):
    import importlib

    from backend.db.background_migrations import UnknownBackgroundMigrationRevisionError

    cli = importlib.import_module("backend.__main__")
    unknown = "aaaaaaaaaaaa"
    known = ("111111111111", "222222222222")
    uvicorn_calls: list[tuple[tuple, dict]] = []

    monkeypatch.setattr(cli, "_configure_database_for_args", lambda _args: None)
    monkeypatch.setattr(cli, "_validate_db_health", lambda: None)
    monkeypatch.setattr(cli, "require_database_current", lambda: None)

    def reject_unknown_revision():
        raise UnknownBackgroundMigrationRevisionError(unknown, known)

    monkeypatch.setattr(
        cli,
        "validate_background_migration_state",
        reject_unknown_revision,
    )
    monkeypatch.setattr(
        cli.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append((args, kwargs)),
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["run"])

    assert exc_info.value.code == 1
    assert uvicorn_calls == []

    stderr = capsys.readouterr().err
    assert "Background migration error:" in stderr
    assert f"Database is at background migration revision {unknown!r}" in stderr
    assert "does not contain that revision" in stderr
