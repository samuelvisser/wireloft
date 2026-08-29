from __future__ import annotations

from pathlib import Path
from typing import Optional
import importlib
import os
import pkgutil

from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from config import get_settings

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


def configure_db() -> None:
    """Configure the global SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal, _db_path

    path = get_settings().database_path
    if _db_path is not None and path.resolve() == _db_path.resolve():
        return

    os.makedirs(path.parent, exist_ok=True)
    engine = create_engine(
        get_settings().database_url,
        connect_args={"check_same_thread": False},
    )

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
