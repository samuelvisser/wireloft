from __future__ import annotations

from pathlib import Path
from typing import Optional
import importlib
import logging
import os
import pkgutil

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings


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


_engine: Optional[Engine] = None
_SessionLocal: Optional[Session] = None
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
