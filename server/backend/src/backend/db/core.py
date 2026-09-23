from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional
import importlib
import logging
import os
import pkgutil
import sqlite3

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DatabaseError, DisconnectionError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings

from .datetime_types import UTCDateTime


logger = logging.getLogger(__name__)

_SQLITE_BUSY_TIMEOUT_SECONDS = 30
_SQLITE_BUSY_TIMEOUT_MS = _SQLITE_BUSY_TIMEOUT_SECONDS * 1_000
_SQLITE_CORRUPTION_CODES = {
    sqlite3.SQLITE_CORRUPT,
    sqlite3.SQLITE_NOTADB,
}
_SQLITE_CORRUPTION_MESSAGES = (
    "database disk image is malformed",
    "database corruption",
    "malformed database schema",
    "file is not a database",
)

naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class DatabaseCorruptionError(RuntimeError):
    """Raised once SQLite reports structural corruption or an unreadable database."""


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)
    type_annotation_map = {datetime: UTCDateTime()}


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_db_path: Optional[Path] = None
_database_corruption_path: Optional[Path] = None
_database_corruption_message: Optional[str] = None
_database_corruption_lock = Lock()


def _iter_exception_chain(exc: BaseException):
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current

        original = getattr(current, "orig", None)
        if isinstance(original, BaseException):
            pending.append(original)
        if isinstance(current.__cause__, BaseException):
            pending.append(current.__cause__)
        if isinstance(current.__context__, BaseException):
            pending.append(current.__context__)


def is_database_corruption_error(exc: BaseException) -> bool:
    """Recognize SQLite corruption through SQLAlchemy wrapper/cause chains."""
    for current in _iter_exception_chain(exc):
        if isinstance(current, DatabaseCorruptionError):
            return True

        sqlite_error_code = getattr(current, "sqlite_errorcode", None)
        if isinstance(sqlite_error_code, int):
            # Extended SQLite result codes retain the primary result code in the
            # low byte. Treat CORRUPT and NOTADB as terminal for this database.
            if (sqlite_error_code & 0xFF) in _SQLITE_CORRUPTION_CODES:
                return True

        message = str(current).casefold()
        if any(token in message for token in _SQLITE_CORRUPTION_MESSAGES):
            return True
    return False


def _mark_database_corrupt(path: Path, message: str) -> None:
    global _database_corruption_path, _database_corruption_message
    with _database_corruption_lock:
        if _database_corruption_message is not None:
            return
        _database_corruption_path = path.resolve()
        _database_corruption_message = message
    logger.critical(
        "SQLite database '%s' is not safe to use: %s. WireLoft will refuse new database sessions.",
        path,
        message,
    )


def _raise_if_database_corrupt(path: Path | None = None) -> None:
    with _database_corruption_lock:
        corrupt_path = _database_corruption_path
        message = _database_corruption_message
    if message is None:
        return
    if path is not None and corrupt_path is not None and path.resolve() != corrupt_path:
        return
    raise DatabaseCorruptionError(
        f"SQLite database '{corrupt_path or path}' is corrupt or unreadable: {message}"
    )


def _clear_corruption_state_for_new_path(path: Path) -> None:
    global _database_corruption_path, _database_corruption_message
    with _database_corruption_lock:
        if _database_corruption_path is None or _database_corruption_path == path.resolve():
            return
        _database_corruption_path = None
        _database_corruption_message = None


def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    """Apply per-connection SQLite settings used by API and worker threads."""
    connection_record.info["pid"] = os.getpid()
    cursor = dbapi_connection.cursor()
    try:
        # For SQLite, enable Foreign Key Support explicitly, according to official docs:
        # https://docs.sqlalchemy.org/en/21/dialects/sqlite.html#sqlite-foreign-keys
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
        # Be explicit about durability instead of depending on how the Python or
        # distro SQLite library was compiled.
        cursor.execute("PRAGMA synchronous=FULL")
    finally:
        cursor.close()


def _checkout_sqlite_connection(dbapi_connection, connection_record, connection_proxy) -> None:
    """Never reuse a pooled SQLite handle in a different process."""
    owner_pid = connection_record.info.get("pid")
    current_pid = os.getpid()
    if owner_pid in (None, current_pid):
        connection_record.info["pid"] = current_pid
        return

    # SQLAlchemy recommends invalidating pooled connections that cross a fork
    # boundary. Uvicorn reload workers are currently spawned, but this protects
    # WireLoft if the launcher/process model changes.
    connection_record.dbapi_connection = connection_proxy.dbapi_connection = None
    raise DisconnectionError(
        f"SQLite connection belongs to pid {owner_pid}; current pid is {current_pid}"
    )


def _handle_sqlite_error(exception_context) -> None:
    original = exception_context.original_exception
    if not is_database_corruption_error(original):
        return
    path = _db_path or get_settings().database_path
    _mark_database_corrupt(path, str(original))


def _verify_sqlite_quick_check(engine: Engine, path: Path) -> None:
    """Catch structural SQLite corruption before background workers can start."""
    try:
        with engine.connect() as connection:
            results = [
                str(row[0])
                for row in connection.exec_driver_sql("PRAGMA quick_check").all()
            ]
    except DatabaseError as exc:
        if not is_database_corruption_error(exc):
            raise
        message = str(exc.orig if exc.orig is not None else exc)
        _mark_database_corrupt(path, message)
        raise DatabaseCorruptionError(
            f"SQLite quick_check could not read '{path}': {message}"
        ) from exc

    if results == ["ok"]:
        return

    details = "; ".join(results[:10]) or "quick_check returned no result"
    _mark_database_corrupt(path, details)
    raise DatabaseCorruptionError(
        f"SQLite quick_check failed for '{path}': {details}"
    )


def _enable_sqlite_wal(engine: Engine) -> None:
    """Enable WAL so long-running readers do not block unrelated writers."""
    with engine.connect() as connection:
        try:
            journal_mode = connection.exec_driver_sql(
                "PRAGMA journal_mode=WAL"
            ).scalar_one()
        except OperationalError as exc:
            if is_database_corruption_error(exc):
                raise
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

    path = get_settings().database_path.resolve()
    _clear_corruption_state_for_new_path(path)
    _raise_if_database_corrupt(path)

    if _db_path is not None and _engine is not None and path == _db_path.resolve():
        return

    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
        _db_path = None

    os.makedirs(path.parent, exist_ok=True)
    engine = create_engine(
        get_settings().database_url,
        connect_args={
            "check_same_thread": False,
            # sqlite3 defaults to five seconds. Background workers and API writes
            # legitimately overlap, so give short writer bursts time to serialize.
            "timeout": _SQLITE_BUSY_TIMEOUT_SECONDS,
        },
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    event.listen(engine, "checkout", _checkout_sqlite_connection)
    event.listen(engine, "handle_error", _handle_sqlite_error)

    try:
        _verify_sqlite_quick_check(engine, path)
        _enable_sqlite_wal(engine)
    except Exception:
        engine.dispose()
        raise

    _engine = engine
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    _db_path = path


def dispose_db() -> None:
    """Close all pooled SQLite handles without forgetting detected corruption."""
    global _engine, _SessionLocal, _db_path
    engine = _engine
    _engine = None
    _SessionLocal = None
    _db_path = None
    if engine is not None:
        engine.dispose()


def get_engine() -> Engine:
    _raise_if_database_corrupt(get_settings().database_path)
    if _engine is None:
        configure_db()
    assert _engine is not None
    return _engine


def get_session() -> Session:
    _raise_if_database_corrupt(get_settings().database_path)
    if _SessionLocal is None:
        configure_db()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db_path() -> Path:
    if _db_path is None:
        configure_db()
    assert _db_path is not None
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

    from backend.db.models import LocalMediaProfile, Show, Episode, Settings
    from backend.db.fake_data import local_media_profiles as seed_local_media_profiles
    from backend.db.fake_data import shows as seed_shows
    from backend.db.fake_data import episodes as seed_episodes
    from backend.db.fake_data import settings as seed_settings

    session = get_session()
    try:
        for media_profile_data in seed_local_media_profiles:
            pk = media_profile_data.get("id")
            if pk is None:
                continue
            if session.get(LocalMediaProfile, pk) is None:
                session.add(LocalMediaProfile(**media_profile_data))

        for show_data in seed_shows:
            pk = show_data.get("id")
            if pk is None:
                continue
            if session.get(Show, pk) is None:
                session.add(Show(**show_data))

        for episode_data in seed_episodes:
            show_id = episode_data.get("show_id")
            episode_id = episode_data.get("id")
            if show_id is None or episode_id is None:
                continue
            existing_episode = (
                session.query(Episode)
                .filter_by(show_id=str(show_id), id=str(episode_id))
                .one_or_none()
            )
            if existing_episode is None:
                session.add(Episode(**episode_data))

        for settings_data in seed_settings:
            pk = settings_data.get("id")
            if pk is None:
                continue
            if session.get(Settings, pk) is None:
                session.add(Settings(**settings_data))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
