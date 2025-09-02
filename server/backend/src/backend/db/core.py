from __future__ import annotations

from pathlib import Path
from typing import Optional
import importlib
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Central declarative Base for all ORM models
Base = declarative_base()

# Internal state for engine and session factory
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_db_path: Optional[Path] = None


def configure(db_path: Path | str) -> None:
    """
    Configure the global SQLAlchemy engine and Session factory.
    Safe to call multiple times; will recreate engine/session if path changes.
    """
    global _engine, _SessionLocal, _db_path

    path = Path(db_path)
    if _db_path is not None and path.resolve() == _db_path.resolve():
        # Already configured to this path, nothing to do
        return

    # Ensure folder exists when we intend to create/connect later
    os.makedirs(path.parent, exist_ok=True)

    # SQLite connect_args recommended for multithreaded apps (e.g., Flask)
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    _engine = engine
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    _db_path = path


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database not configured. Call backend.db.configure(db_path) first.")
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database not configured. Call backend.db.configure(db_path) first.")
    return _SessionLocal()


def get_db_path() -> Path:
    if _db_path is None:
        raise RuntimeError("Database not configured. Call backend.db.configure(db_path) first.")
    return _db_path


def create_all() -> None:
    """
    Import model modules so they are registered with Base, then create tables.
    """
    # Import models explicitly to ensure mappings are registered
    importlib.import_module("backend.db.models.MediaProfile")
    importlib.import_module("backend.db.models.Show")
    importlib.import_module("backend.db.models.Episode")
    importlib.import_module("backend.db.models.Setting")

    Base.metadata.create_all(bind=get_engine())
