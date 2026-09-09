from __future__ import annotations

from types import MethodType

from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, MetaData, String, Table, inspect


SETTINGS_VERSION_TABLE = "settings"
SETTINGS_VERSION_COLUMN = "alembic_version_num"
VERSION_STORAGE_MIGRATION_ATTRIBUTE = "wireloft_version_storage_migration"


def _has_settings_version_table(context: MigrationContext) -> bool:
    if context.as_sql:
        return True
    if context.connection is None:
        return False
    return inspect(context.connection).has_table(
        SETTINGS_VERSION_TABLE,
        schema=context.version_table_schema,
    )


def apply_settings_version_table(context: MigrationContext) -> None:
    """Use ``settings.alembic_version_num`` as Alembic's version store.

    Alembic expects the Python-side key ``version_num``. SQLAlchemy allows that
    key to map to WireLoft's clearer physical column name without making the
    whole Settings table Alembic's logical version table. Keeping Alembic's
    configured version-table name unchanged also means autogenerate continues to
    compare the Settings model normally.
    """
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
