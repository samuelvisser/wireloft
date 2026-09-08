from __future__ import annotations

from alembic import context
from sqlalchemy.engine import make_url

from backend.db.core import Base, get_engine, load_database_models
from config import get_settings


load_database_models()
target_metadata = Base.metadata

_UNMANAGED_TABLES = {"apscheduler_jobs"}


def _include_name(name: str | None, type_: str, _parent_names: dict[str, str]) -> bool:
    if type_ == "table" and name in _UNMANAGED_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    database_url = get_settings().resolved_database_url
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=make_url(database_url).get_backend_name() == "sqlite",
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
            render_as_batch=connection.dialect.name == "sqlite",
            compare_type=True,
            include_name=_include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
