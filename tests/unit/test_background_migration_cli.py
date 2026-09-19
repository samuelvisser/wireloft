from __future__ import annotations

import pytest


def test_background_migration_cli_has_short_alias_and_no_upgrade():
    from backend.__main__ import _parse_args

    args = _parse_args(["migrate", "current"])
    assert args.command == "migrate"
    assert args.background_migration_command == "current"

    long_args = _parse_args(["background-migrations", "history"])
    assert long_args.command == "background-migrations"
    assert long_args.background_migration_command == "history"

    with pytest.raises(SystemExit):
        _parse_args(["migrate", "upgrade"])
