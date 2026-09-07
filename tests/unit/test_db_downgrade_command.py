from __future__ import annotations

from unittest.mock import Mock

import pytest
from alembic.util import CommandError


@pytest.mark.parametrize("revision", ["-1", "d4f0a9c2e713"])
def test_db_downgrade_parser_accepts_relative_and_explicit_revisions(revision: str):
    import backend.__main__ as backend_main

    args = backend_main._parse_args(["db", "downgrade", revision])

    assert args.command == "db"
    assert args.db_command == "downgrade"
    assert args.revision == revision


def test_downgrade_database_delegates_to_alembic(monkeypatch: pytest.MonkeyPatch):
    from backend.db import migrations

    config = object()
    validate = Mock()
    downgrade = Mock()
    monkeypatch.setattr(migrations, "validate_database_migration_state", validate)
    monkeypatch.setattr(migrations, "get_alembic_config", lambda: config)
    monkeypatch.setattr(migrations.command, "downgrade", downgrade)

    migrations.downgrade_database("-1")

    validate.assert_called_once_with()
    downgrade.assert_called_once_with(config, "-1")


def test_downgrade_database_wraps_alembic_errors(monkeypatch: pytest.MonkeyPatch):
    from backend.db import migrations

    monkeypatch.setattr(migrations, "validate_database_migration_state", Mock())
    monkeypatch.setattr(migrations.command, "downgrade", Mock(side_effect=CommandError("bad revision")))

    with pytest.raises(migrations.DatabaseMigrationError, match="bad revision"):
        migrations.downgrade_database("missing")


def test_db_downgrade_handler_reports_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    import backend.__main__ as backend_main

    revision = "d4f0a9c2e713"
    args = backend_main._parse_args(["db", "downgrade", revision])
    downgrade = Mock()
    monkeypatch.setattr(backend_main, "_configure_database_for_args", Mock())
    monkeypatch.setattr(backend_main, "downgrade_database", downgrade)
    monkeypatch.setattr(backend_main, "get_database_status", lambda: ((revision,), "head-revision"))
    monkeypatch.setattr(backend_main, "get_db_path", lambda: "/tmp/wireloft.db")

    backend_main._handle_db_command(args)

    downgrade.assert_called_once_with(revision)
    assert capsys.readouterr().out == (
        "Database downgraded to: d4f0a9c2e713 (/tmp/wireloft.db)\n"
    )
