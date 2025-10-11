from __future__ import annotations

from pathlib import Path
from typing import Optional
import importlib
import os

from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

# include more patterns if you want; the key one is "uq"
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",  # or include multiple: %(column_0_name)s_%(column_1_name)s
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)

# Internal state for engine and session factory
_engine: Optional[Engine] = None
_SessionLocal: Optional[Session] = None
_db_path: Optional[Path] = None


def configure_db() -> None:
    """
    Configure the global SQLAlchemy engine and Session factory.
    Safe to call multiple times; will recreate engine/session if path changes.
    """
    global _engine, _SessionLocal, _db_path

    if os.environ.get("WIRELOFT_DB_PATH", "").strip() == "":
        raise ValueError("WIRELOFT_DB_PATH environment variable is not set.")

    path = Path(os.environ.get("WIRELOFT_DB_PATH"))
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


def create_tables() -> None:
    """
    Import model modules so they are registered with Base, then create tables.
    """
    # Import models explicitly to ensure mappings are registered
    # Order matters due to inheritance: Base tables first, dependents after
    # Base tables
    importlib.import_module("backend.db.models.download_profile.DownloadProfileBase")
    importlib.import_module("backend.db.models.media_download.MediaDownloadBase")
    importlib.import_module("backend.db.models.media_item.MediaItemBase")
    importlib.import_module("backend.db.models.stream_profile.StreamProfileBase")
    importlib.import_module("backend.db.models.stream_worker.StreamWorkerBase")

    # Dependent tables
    importlib.import_module("backend.db.models.download_profile.PodcastDownloadProfile")
    importlib.import_module("backend.db.models.download_profile.SeriesDownloadProfile")
    importlib.import_module("backend.db.models.media_download.EpisodeMediaDownload")
    importlib.import_module("backend.db.models.media_item.Episode")
    importlib.import_module("backend.db.models.media_item.Movie")
    importlib.import_module("backend.db.models.stream_profile.ShowStreamProfile")
    importlib.import_module("backend.db.models.stream_profile.DownloadStreamProfile")
    importlib.import_module("backend.db.models.stream_worker.RssStreamWorker")

    importlib.import_module("backend.db.models.LocalMediaProfile")
    importlib.import_module("backend.db.models.Season")
    importlib.import_module("backend.db.models.Settings")
    importlib.import_module("backend.db.models.Show")

    Base.metadata.create_all(bind=get_engine())


def seed_db() -> None:
    """Seed database using SQLAlchemy ORM and the hardcoded data in backend.data.

    Idempotent: checks for existing rows before inserting to avoid duplicates.
    Assumes the database has already been configured via backend.db.configure.
    It will create tables if they don't exist.
    """
    # Ensure tables are present
    create_tables()

    # Import here to avoid circular imports at module import time
    from backend.db.models.LocalMediaProfile import LocalMediaProfile
    from backend.db.models.Show import Show
    from backend.db.models.Episode import Episode
    from backend.db.models.Settings import Settings
    from backend.db.fake_data import local_media_profiles as seed_local_media_profiles
    from backend.db.fake_data import shows as seed_shows
    from backend.db.fake_data import episodes as seed_episodes
    from backend.db.fake_data import settings as seed_settings

    session = get_session()
    try:
        # Media Profiles: upsert by id
        for mp in seed_local_media_profiles:
            pk = mp.get("id")
            if pk is None:
                continue
            existing = session.get(LocalMediaProfile, pk)
            if existing is None:
                session.add(LocalMediaProfile(**mp))

        # Shows: upsert by id
        for s in seed_shows:
            pk = s.get("id")
            if pk is None:
                continue
            existing = session.get(Show, pk)
            if existing is None:
                session.add(Show(**s))

        # Episodes: upsert by composite (show_id, id)
        for e in seed_episodes:
            sid = e.get("show_id")
            eid = e.get("id")
            if sid is None or eid is None:
                continue
            existing_ep = (
                session.query(Episode)
                .filter_by(show_id=str(sid), id=str(eid))
                .one_or_none()
            )
            if existing_ep is None:
                session.add(Episode(**e))

        # Settings: upsert by id
        for s in seed_settings:
            pk = s.get("id")
            if pk is None:
                continue
            existing = session.get(Settings, pk)
            if existing is None:
                session.add(Settings(**s))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
