from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import importlib
import logging
import os
import pkgutil

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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
_SessionLocal: Optional[sessionmaker] = None
_database_url: Optional[str] = None
_db_path: Optional[Path] = None


def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    """Apply per-connection SQLite settings used by API and worker threads."""
    cursor = dbapi_connection.cursor()
    try:
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


def _resolved_url() -> URL:
    return make_url(get_settings().resolved_database_url)


def _sqlite_path(url: URL) -> Path | None:
    """Return a filesystem path for file-backed SQLite URLs."""
    if url.get_backend_name() != "sqlite":
        return None
    database = url.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return None
    return Path(database)


def get_database_url() -> URL:
    if _engine is None:
        configure_db()
    assert _engine is not None
    return _engine.url


def get_database_label() -> str:
    """Return a log/CLI-safe database identifier with passwords hidden."""
    return get_database_url().render_as_string(hide_password=True)


def get_sqlite_database_path() -> Path | None:
    if _engine is None:
        configure_db()
    return _db_path


def configure_db() -> None:
    """Configure the global SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal, _database_url, _db_path

    url = _resolved_url()
    url_key = url.render_as_string(hide_password=False)
    if _engine is not None and _database_url == url_key:
        return

    sqlite_path = _sqlite_path(url)
    if sqlite_path is not None:
        os.makedirs(sqlite_path.parent, exist_ok=True)

    engine_kwargs: dict[str, object] = {}
    if url.get_backend_name() == "sqlite":
        engine_kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": _SQLITE_BUSY_TIMEOUT_SECONDS,
        }
    else:
        engine_kwargs["pool_pre_ping"] = True

    engine = create_engine(url, **engine_kwargs)
    if url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _configure_sqlite_connection)
        _enable_sqlite_wal(engine)

    old_engine = _engine
    _engine = engine
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _database_url = url_key
    _db_path = sqlite_path
    if old_engine is not None:
        old_engine.dispose()


def get_engine() -> Engine:
    if _engine is None:
        configure_db()
    assert _engine is not None
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        configure_db()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db_path() -> Path:
    """Return the SQLite file path for legacy callers."""
    path = get_sqlite_database_path()
    if path is None:
        raise RuntimeError("The configured database is not a file-backed SQLite database")
    return path


def load_database_models() -> None:
    """Import every model that contributes tables to the shared metadata."""
    package_name = "backend.db.models"
    package = importlib.import_module(package_name)

    if hasattr(package, "__path__"):
        for _, name, _ in pkgutil.walk_packages(package.__path__, package_name + "."):
            importlib.import_module(name)

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
