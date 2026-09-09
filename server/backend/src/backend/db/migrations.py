from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.revision import RangeNotAncestorError, ResolutionError, RevisionError
from alembic.util import CommandError
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Connection

from .alembic_version import (
    SETTINGS_VERSION_COLUMN,
    SETTINGS_VERSION_TABLE,
    VERSION_STORAGE_MIGRATION_ATTRIBUTE,
)
from .core import get_db_path, get_engine


ALEMBIC_DIR = Path(__file__).with_name("alembic")
_UNMANAGED_TABLES = {"apscheduler_jobs"}


class DatabaseMigrationError(RuntimeError):
    """Raised when WireLoft cannot safely use or migrate the database."""


def get_alembic_config(*, allow_version_storage_migration: bool = False) -> Config:
    # Alembic's Config default binds stdout when Alembic itself is imported.
    # Test runners and other embedders can replace and close that stream later,
    # so always bind the currently active stream when creating a config.
    config = Config(stdout=sys.stdout)
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    if allow_version_storage_migration:
        config.attributes[VERSION_STORAGE_MIGRATION_ATTRIBUTE] = True
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


def _settings_revisions(connection: Connection) -> tuple[str, ...]:
    """Read the current revision from WireLoft's only supported version store."""
    inspector = sa_inspect(connection)
    if not inspector.has_table(SETTINGS_VERSION_TABLE):
        raise DatabaseMigrationError(
            f"Database '{get_db_path()}' does not contain current WireLoft migration metadata. "
            "Run 'backend-api db upgrade' to migrate it."
        )

    settings_columns = {
        column["name"] for column in inspector.get_columns(SETTINGS_VERSION_TABLE)
    }
    if SETTINGS_VERSION_COLUMN not in settings_columns:
        raise DatabaseMigrationError(
            f"Database '{get_db_path()}' predates the current WireLoft migration metadata. "
            "Run 'backend-api db upgrade' to migrate it."
        )

    return tuple(
        revision
        for revision in connection.execute(
            text(
                f"SELECT {SETTINGS_VERSION_COLUMN} "
                f"FROM {SETTINGS_VERSION_TABLE} "
                f"WHERE {SETTINGS_VERSION_COLUMN} IS NOT NULL "
                "ORDER BY id"
            )
        ).scalars()
        if revision is not None
    )


def get_current_revisions() -> tuple[str, ...]:
    path = get_db_path()
    if not path.exists():
        return ()

    engine = get_engine()
    if not sa_inspect(engine).get_table_names():
        return ()

    with engine.connect() as connection:
        return _settings_revisions(connection)


def _database_tables() -> set[str]:
    path = get_db_path()
    if not path.exists():
        return set()
    return set(sa_inspect(get_engine()).get_table_names())


def validate_database_migration_state() -> None:
    """Reject application schemas without valid current WireLoft revision state."""
    tables = _database_tables()
    application_tables = tables - _UNMANAGED_TABLES
    if not application_tables:
        return

    current = get_current_revisions()
    if not current:
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


def upgrade_database() -> None:
    """Upgrade old or current WireLoft databases to the current Alembic head."""
    try:
        # The one migration that moved version storage into Settings owns the
        # compatibility required to enter the chain from older databases.
        command.upgrade(
            get_alembic_config(allow_version_storage_migration=True),
            "head",
        )
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc

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
    _validate_downgrade_target(revision)
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
