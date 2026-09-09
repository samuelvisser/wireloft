from __future__ import annotations

from types import MethodType

from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, MetaData, String, Table, inspect
from sqlalchemy.engine import Connection


LEGACY_VERSION_TABLE = "alembic_version"
SETTINGS_VERSION_TABLE = "settings"
SETTINGS_VERSION_COLUMN = "alembic_version_num"
VERSION_STORAGE_REVISION = "d8f3a1c6b205"
_SETTINGS_VERSION_STORAGE_OPTION = "wireloft_settings_version_storage"


def settings_version_column_exists(connection: Connection) -> bool:
    inspector = inspect(connection)
    if not inspector.has_table(SETTINGS_VERSION_TABLE):
        return False
    return SETTINGS_VERSION_COLUMN in {
        column["name"] for column in inspector.get_columns(SETTINGS_VERSION_TABLE)
    }


def use_settings_version_storage(connection: Connection) -> bool:
    """Return whether Alembic should use settings for this command.

    During a migration across the storage boundary both tables can temporarily
    exist. The legacy table wins in that state so the running Alembic context
    keeps using the same version store for the entire command.
    """
    inspector = inspect(connection)
    return (
        settings_version_column_exists(connection)
        and not inspector.has_table(LEGACY_VERSION_TABLE)
    )


def migration_context_options(connection: Connection) -> dict[str, object]:
    if not use_settings_version_storage(connection):
        return {}

    # Keep Alembic's logical version-table name at its default. Autogenerate
    # deliberately excludes whatever table is named by ``version_table``; using
    # "settings" there would make future Settings model changes invisible to
    # ``backend-api db check`` and ``db revision --autogenerate``. The physical
    # table is replaced below instead.
    return {_SETTINGS_VERSION_STORAGE_OPTION: True}


def _has_settings_version_table(context: MigrationContext) -> bool:
    if context.connection is None:
        return False
    return inspect(context.connection).has_table(
        SETTINGS_VERSION_TABLE,
        schema=context.version_table_schema,
    )


def apply_settings_version_table(context: MigrationContext) -> None:
    """Map Alembic's logical version_num key to settings.alembic_version_num.

    Alembic requires its internal version-table object to expose a column keyed
    as ``version_num``. SQLAlchemy lets the Python key differ from the physical
    database column name, so Alembic can keep its normal machinery while the
    database uses the clearer ``alembic_version_num`` name.

    The logical version-table name intentionally remains ``alembic_version`` so
    Alembic autogenerate continues comparing the real Settings table.
    """
    if not context.opts.get(_SETTINGS_VERSION_STORAGE_OPTION):
        return

    context._version = Table(  # noqa: SLF001 - Alembic exposes no public hook for this mapping.
        SETTINGS_VERSION_TABLE,
        MetaData(),
        Column(
            SETTINGS_VERSION_COLUMN,
            String(32),
            key="version_num",
            nullable=True,
        ),
        schema=context.version_table_schema,
    )
    context._has_version_table = MethodType(  # type: ignore[method-assign]  # noqa: SLF001
        _has_settings_version_table,
        context,
    )
