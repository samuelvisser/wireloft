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

    path = get_settings().database_path
    if _db_path is not None and path.resolve() == _db_path.resolve():
        # Already configured to this path, nothing to do
        return

    # Ensure the folder exists when we intend to create/connect later
    os.makedirs(path.parent, exist_ok=True)

    engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})

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
    Auto-discover and import all ORM model modules, then create tables.
    """
    package_name = "backend.db.models"
    package = importlib.import_module(package_name)

    # Recursively import all submodules under backend.db.models so all
    # Declarative mappings are registered with Base.metadata.
    if hasattr(package, "__path__"):
        for _, name, _ in pkgutil.walk_packages(package.__path__, package_name + "."):
            importlib.import_module(name)

    # Ensure mappers are configured before emitting DDL
    from sqlalchemy.orm import configure_mappers
    configure_mappers()

    # Scheduler tables
    try:
        importlib.import_module("task_manager.scheduler.db")
    except Exception:
        # If scheduler package not installed, ignore
        pass

    _recreate_outdated_empty_tables(get_engine())
    Base.metadata.create_all(bind=get_engine())
    _finalize_local_media_profile_type_migration(get_engine())


def _recreate_outdated_empty_tables(engine: Engine) -> None:
    """Poor-man's migration: bring tables whose schema is outdated up to date.

    There is no migration framework (yet). A missing *nullable* column on a
    table that already holds data is added in place with ``ALTER TABLE ...
    ADD COLUMN`` — safe, since SQLite backfills it as NULL on every existing
    row. Anything else (a missing non-nullable column) is only ever applied by
    dropping and recreating the table, and only when it holds no data; on a
    non-empty table it raises so the user can decide what to do instead of
    silently losing data. Only tables listed here are ever considered.
    """
    from sqlalchemy import inspect as sa_inspect, text

    # Child tables first so foreign keys don't block the drop
    migratable = [
        "media_downloads_episode",
        "media_downloads_movie",
        "media_downloads",
        "movies",
        "episodes",
        "stream_profiles_rss",
        "stream_profiles",
        "local_media_profiles",
    ]

    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())

    to_drop: list[str] = []
    for table_name in migratable:
        if table_name not in existing_tables:
            continue
        table = Base.metadata.tables[table_name]
        model_columns = {c.name for c in table.columns}
        db_columns = {c["name"] for c in inspector.get_columns(table_name)}
        missing_columns = model_columns - db_columns
        if not missing_columns:
            continue

        with engine.connect() as conn:
            row_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()

        if not row_count:
            to_drop.append(table_name)
            continue

        non_addable = {
            name for name in missing_columns
            if not table.columns[name].nullable and table.columns[name].server_default is None
        }
        if non_addable:
            raise RuntimeError(
                f"Table '{table_name}' is missing non-nullable columns {sorted(non_addable)} "
                f"but holds {row_count} row(s); refusing to recreate it automatically"
            )

        with engine.begin() as conn:
            from sqlalchemy.schema import CreateColumn

            for name in missing_columns:
                column_ddl = CreateColumn(table.columns[name]).compile(dialect=engine.dialect)
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}"))

    if to_drop:
        with engine.begin() as conn:
            for table_name in to_drop:
                conn.execute(text(f"DROP TABLE {table_name}"))


def _finalize_local_media_profile_type_migration(engine: Engine) -> None:
    """Backfill joined subtype rows and the new composite unique index.

    Profiles created before the type discriminator existed are Show profiles.
    ``_recreate_outdated_empty_tables`` adds that discriminator using its
    server default; this post-create step links those base rows to the joined
    Show table and adds the index that SQLite cannot add via ``ALTER TABLE``.
    """
    from sqlalchemy import inspect as sa_inspect, text

    inspector = sa_inspect(engine)
    tables = set(inspector.get_table_names())
    required = {
        "local_media_profiles",
        "local_media_profiles_show",
        "local_media_profiles_movie",
    }
    if not required.issubset(tables):
        return

    with engine.begin() as conn:
        for profile_type, child_table in (
            ("show", "local_media_profiles_show"),
            ("movie", "local_media_profiles_movie"),
        ):
            conn.execute(text(
                f"INSERT INTO {child_table} (id) "
                "SELECT profile.id FROM local_media_profiles AS profile "
                "WHERE profile.type = :profile_type "
                f"AND NOT EXISTS (SELECT 1 FROM {child_table} AS child WHERE child.id = profile.id)"
            ), {"profile_type": profile_type})

        duplicate = conn.execute(text(
            "SELECT type, output_template, preferred_format, COUNT(*) AS profile_count "
            "FROM local_media_profiles "
            "GROUP BY type, output_template, preferred_format "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicate is not None:
            raise RuntimeError(
                "Local Media Profiles must be unique by type, output template, and preferred format; "
                f"found {duplicate.profile_count} duplicate profiles for type '{duplicate.type}'"
            )

    profile_table = Base.metadata.tables["local_media_profiles"]
    unique_index = next(
        index for index in profile_table.indexes
        if index.name == "uq_local_media_profiles_type_output_template_preferred_format"
    )
    unique_index.create(bind=engine, checkfirst=True)


def seed_db() -> None:
    """Seed database using SQLAlchemy ORM and the hardcoded data in backend.data.

    Idempotent: checks for existing rows before inserting to avoid duplicates.
    Assumes the database has already been configured via backend.db.configure.
    It will create tables if they don't exist.
    """
    # Ensure tables are present
    create_tables()

    # Import ORM classes from the aggregated models package (re-exported in backend.db.models)
    from backend.db.models import LocalMediaProfile, Show, Episode, Settings
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
