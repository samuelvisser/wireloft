from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import importlib
import logging
import os
import pkgutil

from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from config import get_settings

from .datetime_types import UTCDateTime


logger = logging.getLogger(__name__)

_SQLITE_BUSY_TIMEOUT_SECONDS = 30
_SQLITE_BUSY_TIMEOUT_MS = _SQLITE_BUSY_TIMEOUT_SECONDS * 1_000

naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)
    type_annotation_map = {datetime: UTCDateTime()}


_engine: Optional[Engine] = None
_SessionLocal: Optional[Session] = None
_db_path: Optional[Path] = None


def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    """Apply per-connection SQLite settings used by API and worker threads."""
    cursor = dbapi_connection.cursor()
    try:
        # For SQLite, enable Foreign Key Support explicitly, according to official docs:
        # https://docs.sqlalchemy.org/en/21/dialects/sqlite.html#sqlite-foreign-keys
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def _enable_sqlite_wal(engine: Engine) -> None:
    """Enable WAL so long-running readers do not block unrelated writers."""
    with engine.connect() as connection:
        try:
            journal_mode = connection.exec_driver_sql(
                "PRAGMA journal_mode=WAL"
            ).scalar_one()
        except OperationalError:
            # A previous development/reload process can briefly retain a lock.
            # The busy timeout still protects this process; do not make startup
            # fail solely because WAL could not be switched during that window.
            logger.warning(
                "Could not enable SQLite WAL mode; continuing with the current journal mode",
                exc_info=True,
            )
            return

    if str(journal_mode).lower() != "wal":
        logger.warning(
            "SQLite did not enable WAL mode (journal_mode=%s)",
            journal_mode,
        )


def configure_db() -> None:
    """Configure the global SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal, _db_path

    path = get_settings().database_path
    if _db_path is not None and path.resolve() == _db_path.resolve():
        return

    os.makedirs(path.parent, exist_ok=True)
    # A bounded QueuePool is a poor fit for WireLoft's threaded SQLite workload.
    # The scheduler may run as many workers as the old default pool could serve,
    # leaving no connection headroom for API requests. SQLite connections are
    # cheap, and the busy timeout/WAL settings below already govern the actual
    # database contention, so open them on demand and close them with each Session.
    engine = create_engine(
        get_settings().database_url,
        connect_args={
            "check_same_thread": False,
            # sqlite3 defaults to five seconds. Background workers and API writes
            # legitimately overlap, so give short writer bursts time to serialize.
            "timeout": _SQLITE_BUSY_TIMEOUT_SECONDS,
        },
        poolclass=NullPool,
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    _enable_sqlite_wal(engine)

    _engine = engine
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    _db_path = path


def get_engine() -> Engine:
    if _engine is None:
        configure_db()
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        configure_db()
    return _SessionLocal()


def begin_write_transaction(session: Session) -> None:
    """Begin a write-intent transaction before any reads.

    SQLite WAL permits concurrent readers, but a deferred transaction that reads
    before writing can fail with SQLITE_BUSY_SNAPSHOT when another writer commits
    first. BEGIN IMMEDIATE reserves the writer slot up front, allowing SQLite's
    busy timeout to queue these short write transactions instead of failing the
    later read-to-write upgrade.
    """
    if session.in_transaction():
        raise RuntimeError("Write transaction must begin before the session is used")

    bind = session.get_bind()
    if bind.dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    else:
        session.begin()


def get_db_path() -> Path:
    if _db_path is None:
        configure_db()
    return _db_path


def load_database_models() -> None:
    """Import every model that contributes tables to the shared metadata."""
    package_name = "backend.db.models"
    package = importlib.import_module(package_name)

    if hasattr(package, "__path__"):
        for _, name, _ in pkgutil.walk_packages(package.__path__, package_name + "."):
            importlib.import_module(name)

    # The scheduler owns models outside backend.db.models, but they inherit
    # backend.db.Base and therefore belong to the same Alembic schema.
    importlib.import_module("task_manager.scheduler.db")

    from sqlalchemy.orm import configure_mappers

    configure_mappers()


def seed_db() -> None:
    """Seed an already-migrated database with the development/demo data."""
    load_database_models()

    from sqlalchemy import select

    from backend.db.fake_data import episodes_for, shows as seed_shows
    from backend.db.models import Episode, Season, Show

    session = get_session()
    try:
        for show_index, show_data in enumerate(seed_shows, start=1):
            if session.scalar(select(Show.id).where(Show.uuid == show_data["uuid"])) is not None:
                continue
            show = Show(**show_data)
            season = Season(show=show, index=1, slug=f"{show.slug}-episodes", name="Episodes", season_number=1)
            session.add_all([show, season])
            session.flush()
            session.add_all(
                Episode(show_id=show.id, season_id=season.id, **episode_data)
                for episode_data in episodes_for(show_data, show_index)
            )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
