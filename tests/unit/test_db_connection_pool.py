from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.pool import NullPool


def test_configure_db_does_not_bound_sqlite_connections(tmp_path, monkeypatch):
    from backend.db import core

    database_path = tmp_path / "wireloft.db"
    settings = SimpleNamespace(
        database_path=database_path,
        database_url=f"sqlite:///{database_path.as_posix()}",
    )

    monkeypatch.setattr(core, "get_settings", lambda: settings)
    monkeypatch.setattr(core, "_engine", None)
    monkeypatch.setattr(core, "_SessionLocal", None)
    monkeypatch.setattr(core, "_db_path", None)

    core.configure_db()
    engine = core.get_engine()
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()
