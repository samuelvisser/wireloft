from __future__ import annotations

from unittest.mock import Mock

import pytest
from alembic.script.revision import Revision, RevisionMap
from alembic.util import CommandError


def _branched_script_directory() -> Mock:
    revisions = RevisionMap(
        lambda: iter(
            [
                Revision("base_revision", None),
                Revision("left_revision", "base_revision"),
                Revision("right_revision", "base_revision"),
                Revision("left_head", "left_revision"),
                Revision("right_head", "right_revision"),
            ]
        )
    )
    scripts = Mock()
    scripts.iterate_revisions.side_effect = revisions.iterate_revisions
    return scripts


@pytest.mark.parametrize("revision", ["-1", "d4f0a9c2e713"])
def test_db_downgrade_parser_accepts_relative_and_explicit_revisions(revision: str):
    import backend.__main__ as backend_main

    args = backend_main._parse_args(["db", "downgrade", revision])

    assert args.command == "db"
    assert args.db_command == "downgrade"
    assert args.revision == revision


@pytest.mark.parametrize("revision", ["-1", "left_revision"])
def test_downgrade_database_uses_database_path_with_multiple_script_heads(
    revision: str,
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.db import migrations

    config = object()
    current = ("left_head",)
    scripts = _branched_script_directory()
    validate = Mock()
    downgrade = Mock()
    monkeypatch.setattr(migrations, "validate_database_migration_state", validate)
    monkeypatch.setattr(migrations, "get_current_revisions", lambda: current)
    monkeypatch.setattr(migrations, "_script_directory", lambda: scripts)
    monkeypatch.setattr(migrations, "get_alembic_config", lambda: config)
    monkeypatch.setattr(migrations.command, "downgrade", downgrade)

    migrations.downgrade_database(revision)

    validate.assert_called_once_with()
    scripts.iterate_revisions.assert_called_once_with(
        current,
        revision,
        select_for_downgrade=True,
    )
    downgrade.assert_called_once_with(config, revision)


def test_downgrade_database_rejects_revision_on_another_head(
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.db import migrations

    scripts = _branched_script_directory()
    downgrade = Mock()
    monkeypatch.setattr(migrations, "validate_database_migration_state", Mock())
    monkeypatch.setattr(migrations, "get_current_revisions", lambda: ("left_head",))
    monkeypatch.setattr(migrations, "_script_directory", lambda: scripts)
    monkeypatch.setattr(migrations.command, "downgrade", downgrade)

    with pytest.raises(
        migrations.DatabaseMigrationError,
        match="requested revision is not an ancestor",
    ):
        migrations.downgrade_database("right_revision")

    downgrade.assert_not_called()


def test_downgrade_database_rejects_relative_target_with_multiple_database_heads(
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.db import migrations

    scripts = _branched_script_directory()
    downgrade = Mock()
    monkeypatch.setattr(migrations, "validate_database_migration_state", Mock())
    monkeypatch.setattr(
        migrations,
        "get_current_revisions",
        lambda: ("left_head", "right_head"),
    )
    monkeypatch.setattr(migrations, "_script_directory", lambda: scripts)
    monkeypatch.setattr(migrations.command, "downgrade", downgrade)

    with pytest.raises(
        migrations.DatabaseMigrationError,
        match="Relative downgrade '-1' is ambiguous",
    ):
        migrations.downgrade_database("-1")

    scripts.iterate_revisions.assert_not_called()
    downgrade.assert_not_called()


def test_downgrade_database_wraps_alembic_errors(monkeypatch: pytest.MonkeyPatch):
    from backend.db import migrations

    scripts = _branched_script_directory()
    monkeypatch.setattr(migrations, "validate_database_migration_state", Mock())
    monkeypatch.setattr(migrations, "get_current_revisions", lambda: ("left_head",))
    monkeypatch.setattr(migrations, "_script_directory", lambda: scripts)
    monkeypatch.setattr(
        migrations.command,
        "downgrade",
        Mock(side_effect=CommandError("bad revision")),
    )

    with pytest.raises(migrations.DatabaseMigrationError, match="bad revision"):
        migrations.downgrade_database("left_revision")


def test_db_downgrade_handler_reports_result_without_requiring_single_script_head(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    import backend.__main__ as backend_main

    revision = "left_revision"
    args = backend_main._parse_args(["db", "downgrade", revision])
    downgrade = Mock()
    monkeypatch.setattr(backend_main, "_configure_database_for_args", Mock())
    monkeypatch.setattr(backend_main, "downgrade_database", downgrade)
    monkeypatch.setattr(backend_main, "get_current_revisions", lambda: (revision,))
    monkeypatch.setattr(
        backend_main,
        "get_database_status",
        Mock(side_effect=AssertionError("must not require a single Alembic head")),
    )
    monkeypatch.setattr(backend_main, "get_db_path", lambda: "/tmp/wireloft.db")

    backend_main._handle_db_command(args)

    downgrade.assert_called_once_with(revision)
    assert capsys.readouterr().out == (
        "Database downgraded to: left_revision (/tmp/wireloft.db)\n"
    )


def test_db_current_handler_reports_multiple_script_heads(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    import backend.__main__ as backend_main

    args = backend_main._parse_args(["db", "current"])
    validate = Mock()
    monkeypatch.setattr(backend_main, "_configure_database_for_args", Mock())
    monkeypatch.setattr(backend_main, "validate_database_migration_state", validate)
    monkeypatch.setattr(backend_main, "get_current_revisions", lambda: ("left_head",))
    monkeypatch.setattr(
        backend_main,
        "get_head_revisions",
        lambda: ("left_head", "right_head"),
    )

    backend_main._handle_db_command(args)

    validate.assert_called_once_with()
    assert capsys.readouterr().out == (
        "Current database revision: left_head\n"
        "Latest WireLoft revisions:  left_head, right_head\n"
        "Status: multiple Alembic heads (2)\n"
    )
