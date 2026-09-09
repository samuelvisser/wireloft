from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.script.revision import RangeNotAncestorError, ResolutionError, RevisionError
from alembic.util import CommandError
from sqlalchemy import Column, MetaData, String, Table, inspect as sa_inspect, select, text

from .alembic_version import (
    LEGACY_VERSION_TABLE,
    SETTINGS_VERSION_COLUMN,
    SETTINGS_VERSION_TABLE,
    VERSION_STORAGE_REVISION,
    apply_settings_version_table,
    migration_context_options,
    settings_version_column_exists,
    use_settings_version_storage,
)
from .core import get_db_path, get_engine


ALEMBIC_DIR = Path(__file__).with_name("alembic")
# Retained as the public constant for callers that still need the legacy name.
ALEMBIC_VERSION_TABLE = LEGACY_VERSION_TABLE


class DatabaseMigrationError(RuntimeError):
    """Raised when WireLoft cannot safely use or migrate the database."""


def get_alembic_config() -> Config:
    # Alembic's Config default binds stdout when Alembic itself is imported.
    # Test runners and other embedders can replace and close that stream later,
    # so always bind the currently active stream when creating a config.
    config = Config(stdout=sys.stdout)
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(get_alembic_config())


def get_head_revisions() -> tuple[str, ...]:
    return tuple(_script_directory().get_heads())


def get_head_revision() -> str:
    heads = get_head_revisions()
    if len(heads) != 1:
        raise DatabaseMigrationError(
            f"WireLoft must have exactly one Alembic head, found {len(heads)}: {heads}"
        )
    return heads[0]


def _migration_context(connection) -> MigrationContext:
    context = MigrationContext.configure(
        connection,
        opts=migration_context_options(connection),
    )
    apply_settings_version_table(context)
    return context


def get_current_revisions() -> tuple[str, ...]:
    path = get_db_path()
    if not path.exists():
        return ()

    with get_engine().connect() as connection:
        return tuple(
            revision
            for revision in _migration_context(connection).get_current_heads()
            if revision is not None
        )


def _database_tables() -> set[str]:
    path = get_db_path()
    if not path.exists():
        return set()
    return set(sa_inspect(get_engine()).get_table_names())


def _database_has_version_storage(tables: set[str]) -> bool:
    if LEGACY_VERSION_TABLE in tables:
        return True
    if SETTINGS_VERSION_TABLE not in tables:
        return False
    with get_engine().connect() as connection:
        return settings_version_column_exists(connection)


def validate_database_migration_state() -> None:
    """Reject existing application schemas that Alembic does not own."""
    tables = _database_tables()
    if not tables:
        return

    if not _database_has_version_storage(tables):
        raise DatabaseMigrationError(
            f"Database '{get_db_path()}' contains tables but is not Alembic-managed. "
            "Delete/recreate it, or manually stamp the correct Alembic revision before starting WireLoft."
        )

    current = get_current_revisions()
    application_tables = tables - {LEGACY_VERSION_TABLE}
    if application_tables and not current:
        raise DatabaseMigrationError(
            f"Database '{get_db_path()}' contains WireLoft tables but its Alembic revision is empty. "
            "Refusing to guess the schema version."
        )

    scripts = _script_directory()
    for revision in current:
        try:
            scripts.get_revision(revision)
        except (CommandError, ResolutionError) as exc:
            raise DatabaseMigrationError(
                f"Database '{get_db_path()}' references unknown Alembic revision '{revision}'."
            ) from exc


def require_database_current() -> None:
    validate_database_migration_state()
    required = get_head_revision()
    current = get_current_revisions()
    if current != (required,):
        current_label = ", ".join(current) if current else "base / not initialized"
        raise DatabaseMigrationError(
            "Database schema is not current. "
            f"Current: {current_label}. Required: {required}. "
            "Run 'backend-api db upgrade'."
        )


def initialize_database() -> None:
    if _database_tables():
        raise DatabaseMigrationError(
            f"Database '{get_db_path()}' is not empty; db init only supports new or empty databases."
        )
    upgrade_database()


def _legacy_version_table() -> Table:
    return Table(
        LEGACY_VERSION_TABLE,
        MetaData(),
        Column("version_num", String(32), primary_key=True, nullable=False),
    )


def _activate_settings_version_storage() -> None:
    """Move the final Alembic head from its legacy table onto Settings.

    The d8 migration adds ``settings.alembic_version_num`` while Alembic is still
    using its legacy table for that command. Moving the value after the command
    finishes avoids changing Alembic's version table underneath a running
    migration context.
    """
    with get_engine().begin() as connection:
        inspector = sa_inspect(connection)
        if not inspector.has_table(LEGACY_VERSION_TABLE):
            return
        if not settings_version_column_exists(connection):
            return

        revisions = tuple(
            connection.execute(
                select(_legacy_version_table().c.version_num)
            ).scalars()
        )
        if len(revisions) != 1:
            raise DatabaseMigrationError(
                "Cannot move Alembic version tracking into settings unless the database "
                f"has exactly one current revision; found {revisions}."
            )

        settings_rows = connection.execute(text(
            f"SELECT id, {SETTINGS_VERSION_COLUMN} "
            f"FROM {SETTINGS_VERSION_TABLE} ORDER BY id"
        )).mappings().all()
        if len(settings_rows) != 1:
            raise DatabaseMigrationError(
                "The settings table must contain exactly one application settings row "
                "before Alembic version tracking can be stored there."
            )

        current_value = settings_rows[0][SETTINGS_VERSION_COLUMN]
        revision = revisions[0]
        if current_value not in (None, revision):
            raise DatabaseMigrationError(
                "settings.alembic_version_num disagrees with the legacy Alembic version table."
            )

        connection.execute(
            text(
                f"UPDATE {SETTINGS_VERSION_TABLE} "
                f"SET {SETTINGS_VERSION_COLUMN} = :revision WHERE id = :settings_id"
            ),
            {"revision": revision, "settings_id": settings_rows[0]["id"]},
        )
        Table(
            LEGACY_VERSION_TABLE,
            MetaData(),
            autoload_with=connection,
        ).drop(connection)


def _activate_legacy_version_storage() -> None:
    """Prepare a downgrade across d8 without deleting the Settings row.

    d8's downgrade removes ``settings.alembic_version_num``. Alembic therefore
    has to switch back to its legacy table *before* that migration starts, so its
    HeadMaintainer never tries to update a column the migration just removed.
    """
    with get_engine().begin() as connection:
        inspector = sa_inspect(connection)
        if inspector.has_table(LEGACY_VERSION_TABLE):
            return
        if not use_settings_version_storage(connection):
            return

        revisions = tuple(
            connection.execute(
                text(
                    f"SELECT {SETTINGS_VERSION_COLUMN} "
                    f"FROM {SETTINGS_VERSION_TABLE} "
                    f"WHERE {SETTINGS_VERSION_COLUMN} IS NOT NULL"
                )
            ).scalars()
        )
        if len(revisions) != 1:
            raise DatabaseMigrationError(
                "Cannot move Alembic version tracking out of settings unless the database "
                f"has exactly one current revision; found {revisions}."
            )

        version_table = _legacy_version_table()
        version_table.create(connection)
        connection.execute(
            version_table.insert().values(version_num=revisions[0])
        )


def upgrade_database() -> None:
    validate_database_migration_state()
    try:
        command.upgrade(get_alembic_config(), "head")
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc

    # A database upgrading from c5 (or an empty database) runs the command with
    # Alembic's legacy table. d8 adds the Settings column, then this atomic handoff
    # stores the final head there and removes the dedicated version table.
    _activate_settings_version_storage()
    require_database_current()


def _is_relative_downgrade(revision: str) -> bool:
    return revision.startswith("-") and revision[1:].isdigit()


def _validate_downgrade_target(revision: str) -> list:
    """Verify the target is reachable by downgrading from the DB's current path."""
    current = get_current_revisions()
    if not current:
        raise DatabaseMigrationError(
            f"Database '{get_db_path()}' has no current Alembic revision to downgrade."
        )

    if len(current) > 1 and _is_relative_downgrade(revision):
        current_label = ", ".join(current)
        raise DatabaseMigrationError(
            f"Database has multiple current Alembic revisions ({current_label}). "
            f"Relative downgrade '{revision}' is ambiguous; specify an explicit target revision."
        )

    current_label = ", ".join(current)
    try:
        # Start traversal at the revision(s) actually stored in the database, not
        # at the script directory's global head(s). Unrelated Alembic branches
        # therefore do not prevent recovery of the branch this database is on.
        return list(
            _script_directory().iterate_revisions(
                current,
                revision,
                select_for_downgrade=True,
            )
        )
    except RangeNotAncestorError as exc:
        raise DatabaseMigrationError(
            f"Cannot downgrade database from {current_label} to '{revision}': "
            "the requested revision is not an ancestor of the database's current revision(s)."
        ) from exc
    except (CommandError, RevisionError) as exc:
        raise DatabaseMigrationError(
            f"Cannot downgrade database from {current_label} to '{revision}': {exc}"
        ) from exc


def downgrade_database(revision: str) -> None:
    validate_database_migration_state()
    downgrade_path = _validate_downgrade_target(revision)

    # If this command will execute d8's downgrade, switch version storage first.
    # The entire Alembic command then consistently uses the legacy table, even if
    # it continues through older revisions in the same invocation.
    if any(item.revision == VERSION_STORAGE_REVISION for item in downgrade_path):
        _activate_legacy_version_storage()

    try:
        command.downgrade(get_alembic_config(), revision)
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc


def check_database() -> None:
    """Verify both the DB revision and ORM-to-migration schema synchronization."""
    require_database_current()
    try:
        command.check(get_alembic_config())
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc


def create_revision(message: str) -> None:
    require_database_current()
    try:
        command.revision(get_alembic_config(), message=message, autogenerate=True)
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc


def get_database_status() -> tuple[tuple[str, ...], str]:
    validate_database_migration_state()
    return get_current_revisions(), get_head_revision()


def show_history() -> None:
    try:
        command.history(get_alembic_config(), verbose=True)
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc
