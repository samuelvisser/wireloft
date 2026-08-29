from __future__ import annotations

from alembic import context

from backend.db.core import Base, get_engine, load_database_models
from config import get_settings


load_database_models()
target_metadata = Base.metadata

# APScheduler's SQLAlchemy job store owns this table itself. It deliberately
# lives in the same database, but it is not part of WireLoft's ORM schema and
# must never be considered a candidate for Alembic removal/autogeneration.
_UNMANAGED_TABLES = {"apscheduler_jobs"}


def _include_name(name: str | None, type_: str, _parent_names: dict[str, str]) -> bool:
    if type_ == "table" and name in _UNMANAGED_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
        include_name=_include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            include_name=_include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
