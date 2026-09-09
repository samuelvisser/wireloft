from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.revision import RangeNotAncestorError, ResolutionError, RevisionError
from alembic.util import CommandError
from sqlalchemy import Column, MetaData, String, Table, inspect as sa_inspect, select, text
from sqlalchemy.engine import Connection

from .core import get_db_path, get_engine


ALEMBIC_DIR = Path(__file__).with_name("alembic")
ALEMBIC_VERSION_TABLE = "alembic_version"
SETTINGS_VERSION_TABLE = "settings"
SETTINGS_VERSION_COLUMN = "alembic_version_num"


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


def _legacy_version_table() -> Table:
    return Table(
        ALEMBIC_VERSION_TABLE,
        MetaData(),
        Column("version_num", String(32), primary_key=True, nullable=False),
    )


def _settings_version_column_exists(connection: Connection) -> bool:
    inspector = sa_inspect(connection)
    if not inspector.has_table(SETTINGS_VERSION_TABLE):
        return False
    return SETTINGS_VERSION_COLUMN in {
        column["name"] for column in inspector.get_columns(SETTINGS_VERSION_TABLE)
    }


def _legacy_revisions(connection: Connection) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            select(_legacy_version_table().c.version_num)
        ).scalars()
    )


def _settings_revisions(connection: Connection) -> tuple[str, ...]:
    if not _settings_version_column_exists(connection):
        return ()
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


def _stored_revisions(connection: Connection) -> tuple[str, ...]:
    """Read the authoritative database revision without involving Alembic internals.

    A temporary ``alembic_version`` table may exist while a migration command is
    running or after an interrupted command. In that case it is authoritative;
    otherwise the persistent revision lives on the singleton Settings row.
    """
    if sa_inspect(connection).has_table(ALEMBIC_VERSION_TABLE):
        return _legacy_revisions(connection)
    return _settings_revisions(connection)


def get_current_revisions() -> tuple[str, ...]:
    path = get_db_path()
    if not path.exists():
        return ()

    with get_engine().connect() as connection:
        return _stored_revisions(connection)


def _database_tables() -> set[str]:
    path = get_db_path()
    if not path.exists():
        return set()
    return set(sa_inspect(get_engine()).get_table_names())


def _database_has_version_storage(tables: set[str]) -> bool:
    if ALEMBIC_VERSION_TABLE in tables:
        return True
    if SETTINGS_VERSION_TABLE not in tables:
        return False
    with get_engine().connect() as connection:
        return _settings_version_column_exists(connection)


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
    application_tables = tables - {ALEMBIC_VERSION_TABLE}
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


def _materialize_alembic_version_table() -> bool:
    """Give Alembic its native version table for the duration of a DB command.

    Alembic treats its version table as an implementation detail that it may
    insert into, update, or delete from. The Settings table is application data,
    so making Alembic operate on it directly is unsafe. WireLoft instead keeps
    the revision persistently in Settings and materializes Alembic's normal table
    only while an Alembic command is executing.

    Returns whether this call created the temporary table.
    """
    with get_engine().begin() as connection:
        inspector = sa_inspect(connection)
        if inspector.has_table(ALEMBIC_VERSION_TABLE):
            return False
        if not _settings_version_column_exists(connection):
            return False

        settings_rows = connection.execute(text(
            f"SELECT id, {SETTINGS_VERSION_COLUMN} "
            f"FROM {SETTINGS_VERSION_TABLE} ORDER BY id"
        )).mappings().all()
        if len(settings_rows) != 1:
            raise DatabaseMigrationError(
                "The settings table must contain exactly one application settings row "
                "before Alembic version tracking can be materialized."
            )

        revision = settings_rows[0][SETTINGS_VERSION_COLUMN]
        if revision is None:
            raise DatabaseMigrationError(
                "settings.alembic_version_num is empty; refusing to guess the database revision."
            )

        version_table = _legacy_version_table()
        version_table.create(connection)
        connection.execute(version_table.insert().values(version_num=revision))
        return True


def _persist_settings_version_storage() -> None:
    """Persist Alembic's resulting revision in Settings and remove its table.

    Before revision d8 the Settings column does not exist, so the normal Alembic
    table remains in place. At d8 and later, the final database contains only
    ``settings.alembic_version_num``.
    """
    with get_engine().begin() as connection:
        inspector = sa_inspect(connection)
        if not inspector.has_table(ALEMBIC_VERSION_TABLE):
            return
        if not _settings_version_column_exists(connection):
            return

        revisions = _legacy_revisions(connection)
        if len(revisions) != 1:
            raise DatabaseMigrationError(
                "WireLoft can only persist one current Alembic revision in settings; "
                f"found {revisions}."
            )

        settings_rows = connection.execute(text(
            f"SELECT id FROM {SETTINGS_VERSION_TABLE} ORDER BY id"
        )).scalars().all()
        if len(settings_rows) != 1:
            raise DatabaseMigrationError(
                "The settings table must contain exactly one application settings row "
                "before Alembic version tracking can be persisted there."
            )

        connection.execute(
            text(
                f"UPDATE {SETTINGS_VERSION_TABLE} "
                f"SET {SETTINGS_VERSION_COLUMN} = :revision WHERE id = :settings_id"
            ),
            {"revision": revisions[0], "settings_id": settings_rows[0]},
        )
        Table(
            ALEMBIC_VERSION_TABLE,
            MetaData(),
            autoload_with=connection,
        ).drop(connection)


def upgrade_database() -> None:
    validate_database_migration_state()
    _materialize_alembic_version_table()
    try:
        command.upgrade(get_alembic_config(), "head")
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc

    _persist_settings_version_storage()
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
    _materialize_alembic_version_table()
    try:
        command.downgrade(get_alembic_config(), revision)
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc

    _persist_settings_version_storage()


def check_database() -> None:
    """Verify both the DB revision and ORM-to-migration schema synchronization."""
    require_database_current()
    materialized = _materialize_alembic_version_table()
    try:
        command.check(get_alembic_config())
    except CommandError as exc:
        if materialized:
            _persist_settings_version_storage()
        raise DatabaseMigrationError(str(exc)) from exc
    if materialized:
        _persist_settings_version_storage()


def create_revision(message: str) -> None:
    require_database_current()
    materialized = _materialize_alembic_version_table()
    try:
        command.revision(get_alembic_config(), message=message, autogenerate=True)
    except CommandError as exc:
        if materialized:
            _persist_settings_version_storage()
        raise DatabaseMigrationError(str(exc)) from exc
    if materialized:
        _persist_settings_version_storage()


def get_database_status() -> tuple[tuple[str, ...], str]:
    validate_database_migration_state()
    return get_current_revisions(), get_head_revision()


def show_history() -> None:
    try:
        command.history(get_alembic_config(), verbose=True)
    except CommandError as exc:
        raise DatabaseMigrationError(str(exc)) from exc
