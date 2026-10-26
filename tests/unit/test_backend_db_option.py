from __future__ import annotations

from pathlib import Path

import pytest


def test_db_option_points_db_commands_at_that_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.__main__ as backend_main
    from backend.db import core
    from config import registry

    # Start from settings that name another database, like a normal install.
    default_path = tmp_path / "default.db"
    monkeypatch.setattr(registry, "_SETTINGS", registry.get_settings().model_copy(update={"database_path": default_path}))
    monkeypatch.setenv("WL_DATABASE_PATH", str(default_path))
    for name in ("_engine", "_SessionLocal", "_db_path"):
        monkeypatch.setattr(core, name, None)

    chosen = tmp_path / "chosen.db"
    backend_main.main(["db", "init", "--db", str(chosen)])

    assert chosen.is_file()
    assert not default_path.exists()
    assert core.get_db_path() == chosen
