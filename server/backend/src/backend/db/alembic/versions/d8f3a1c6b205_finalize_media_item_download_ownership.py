"""Finalize media-item naming, download ownership, and database metadata.

Revision ID: d8f3a1c6b205
Revises: c5a9e2f7b104
"""

from alembic import op
from alembic.runtime.migration import MigrationContext
from alembic.util import CommandError
import sqlalchemy as sa

from backend.db.alembic_version import (
    SETTINGS_VERSION_COLUMN,
    SETTINGS_VERSION_TABLE,
    apply_settings_version_table,
)


revision = "d8f3a1c6b205"
down_revision = "c5a9e2f7b104"
branch_labels = None
depends_on = None


_LEGACY_VERSION_TABLE = "alembic_version"
_UNMANAGED_TABLES = {"apscheduler_jobs"}


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _legacy_version_table() -> sa.Table:
    return sa.Table(
        _LEGACY_VERSION_TABLE,
        sa.MetaData(),
        sa.Column("version_num", sa.String(32), primary_key=True, nullable=False),
    )


def _legacy_revisions(bind) -> tuple[str, ...]:
    return tuple(
        bind.execute(
            sa.select(_legacy_version_table().c.version_num)
        ).scalars()
    )


def _settings_version_rows(bind) -> list[dict]:
    return list(bind.execute(sa.text(
        f"SELECT id, {SETTINGS_VERSION_COLUMN} "
        f"FROM {SETTINGS_VERSION_TABLE} ORDER BY id"
    )).mappings())


def configure_version_storage_for_upgrade(context: MigrationContext) -> None:
    """Select version storage only while upgrading across this historical boundary.

    Current WireLoft databases always use ``settings.alembic_version_num``. The
    upgrade command can also receive a database created before this revision,
    where Alembic still has its native ``alembic_version`` table. Keep that
    compatibility here, beside the migration that performs the one-time handoff.
    """
    connection = context.connection
    if connection is None:
        return

    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    application_tables = tables - _UNMANAGED_TABLES

    # A fresh database starts with Alembic's native table. This migration switches
    # the same running MigrationContext to Settings once it reaches this revision.
    if not application_tables:
        return

    settings_has_version = (
        SETTINGS_VERSION_TABLE in tables
        and SETTINGS_VERSION_COLUMN in _column_names(connection, SETTINGS_VERSION_TABLE)
    )
    legacy_exists = _LEGACY_VERSION_TABLE in tables

    # Both can exist after an interrupted handoff. In that state Alembic must
    # resume from the legacy value; upgrade() will complete the transfer below.
    if legacy_exists:
        return

    if not settings_has_version:
        raise CommandError(
            "Database contains tables but is not Alembic-managed by a supported WireLoft schema. "
            "Delete/recreate it, or manually stamp the correct Alembic revision before upgrading."
        )

    settings_rows = _settings_version_rows(connection)
    if len(settings_rows) != 1 or settings_rows[0][SETTINGS_VERSION_COLUMN] is None:
        raise CommandError(
            "settings.alembic_version_num must contain exactly one current revision before upgrading."
        )

    apply_settings_version_table(context)


def _handoff_version_storage(bind) -> None:
    """Move Alembic's live MigrationContext from its old table into Settings."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_LEGACY_VERSION_TABLE):
        # A downgrade followed by a re-upgrade, or an interrupted handoff after
        # the old table was already dropped, is already using current storage.
        apply_settings_version_table(op.get_context())
        return

    revisions = _legacy_revisions(bind)
    if len(revisions) != 1:
        raise RuntimeError(
            "Cannot move Alembic version tracking into settings unless the database "
            f"has exactly one current revision; found {revisions}."
        )

    current_revision = revisions[0]
    if current_revision != down_revision:
        raise RuntimeError(
            "The Alembic version-storage handoff can only run while upgrading "
            f"from {down_revision}; found {current_revision}."
        )

    settings_rows = _settings_version_rows(bind)
    if len(settings_rows) != 1:
        raise RuntimeError(
            "The settings table must contain exactly one row before Alembic "
            "version tracking can be moved into it."
        )

    stored_revision = settings_rows[0][SETTINGS_VERSION_COLUMN]
    if stored_revision not in (None, current_revision):
        raise RuntimeError(
            "settings.alembic_version_num disagrees with the legacy Alembic version table."
        )

    bind.execute(
        sa.text(
            f"UPDATE {SETTINGS_VERSION_TABLE} "
            f"SET {SETTINGS_VERSION_COLUMN} = :revision WHERE id = :settings_id"
        ),
        {
            "revision": current_revision,
            "settings_id": settings_rows[0]["id"],
        },
    )

    # HeadMaintainer updates the revision *after* upgrade() returns. Switch the
    # running context before that happens so c5 -> d8, and every later revision
    # in the same command, is written directly to Settings.
    _legacy_version_table().drop(bind)
    apply_settings_version_table(op.get_context())


def _rename_series_profile_fk_column(old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    columns = _column_names(bind, "download_profile_series_seasons")

    if new_name in columns:
        if old_name in columns:
            raise RuntimeError(
                "download_profile_series_seasons contains both the old and new "
                "series-profile foreign-key columns"
            )
        return
    if old_name not in columns:
        raise RuntimeError(
            "download_profile_series_seasons contains neither expected "
            f"series-profile foreign-key column ({old_name!r}, {new_name!r})"
        )

    with op.batch_alter_table("download_profile_series_seasons") as batch_op:
        batch_op.alter_column(
            old_name,
            new_column_name=new_name,
            existing_type=sa.Integer(),
            existing_nullable=True,
        )


def _rename_table_if_needed(bind, old_name: str, new_name: str) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    old_exists = old_name in tables
    new_exists = new_name in tables

    if new_exists and not old_exists:
        return
    if old_exists and not new_exists:
        op.rename_table(old_name, new_name)
        return
    if old_exists and new_exists:
        raise RuntimeError(
            f"Cannot resume migration because both {old_name!r} and {new_name!r} exist"
        )
    raise RuntimeError(
        f"Cannot resume migration because neither {old_name!r} nor {new_name!r} exists"
    )


def _drop_column_if_present(bind, table_name: str, column_name: str) -> None:
    if column_name in _column_names(bind, table_name):
        op.drop_column(table_name, column_name)


def _add_column_if_missing(bind, table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(bind, table_name):
        op.add_column(table_name, column)


def _episode_table_name(bind) -> str:
    tables = set(sa.inspect(bind).get_table_names())
    old_exists = "media_items_episodes" in tables
    new_exists = "media_items_episode" in tables

    if old_exists == new_exists:
        raise RuntimeError(
            "Expected exactly one of 'media_items_episodes' or 'media_items_episode'"
        )
    return "media_items_episodes" if old_exists else "media_items_episode"


def upgrade() -> None:
    bind = op.get_bind()

    # SQLite can leave DDL from an interrupted migration in place even when the
    # Alembic revision remains at c5. Every schema operation in this revision is
    # therefore restart-safe so `backend-api db upgrade` can resume the migration.
    _add_column_if_missing(
        bind,
        SETTINGS_VERSION_TABLE,
        sa.Column(SETTINGS_VERSION_COLUMN, sa.String(length=32), nullable=True),
    )

    _rename_series_profile_fk_column(
        "series_download_profile_id",
        "download_profiles_series_id",
    )

    # Download timestamps belong to the concrete MediaDownload artifact. A media
    # item can have multiple downloads (one per Local Media Profile), so a single
    # item-level timestamp is ambiguous. Redownload attempts remain represented
    # by the canonical TaskRun history for each MediaDownload.
    _drop_column_if_present(bind, "media_items", "downloaded_date")
    _drop_column_if_present(bind, _episode_table_name(bind), "redownloaded_date")

    # Match the established joined-inheritance naming used by media_downloads:
    # one singular subtype suffix per concrete table.
    _rename_table_if_needed(bind, "media_items_episodes", "media_items_episode")
    _rename_table_if_needed(bind, "media_items_movie_extras", "media_items_movie_extra")
    _rename_table_if_needed(bind, "media_items_movies", "media_items_movie")

    # HasMetadataMixin uses the physical table name as its discriminator.
    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episode' "
        "WHERE parent_table = 'media_items_episodes'"
    ))

    # This is the one historical point where WireLoft changes Alembic's version
    # store. Keep the compatibility and transfer logic in this migration rather
    # than teaching current migration services about both storage schemes.
    _handoff_version_storage(bind)


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text(
        "UPDATE metadata SET parent_table = 'media_items_episodes' "
        "WHERE parent_table = 'media_items_episode'"
    ))

    _rename_table_if_needed(bind, "media_items_movie_extra", "media_items_movie_extras")
    _rename_table_if_needed(bind, "media_items_movie", "media_items_movies")
    _rename_table_if_needed(bind, "media_items_episode", "media_items_episodes")

    # The removed aggregate timestamps cannot be reconstructed unambiguously
    # when multiple MediaDownloads exist, so downgrade restores nullable columns.
    _add_column_if_missing(
        bind,
        "media_items_episodes",
        sa.Column("redownloaded_date", sa.DateTime(), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "media_items",
        sa.Column("downloaded_date", sa.DateTime(), nullable=True),
    )

    _rename_series_profile_fk_column(
        "download_profiles_series_id",
        "series_download_profile_id",
    )

    # Version tracking is migration-runner infrastructure rather than application
    # schema state. Once this migration has moved it to Settings, keep it there
    # even when the application schema is downgraded below d8. That lets the
    # current WireLoft CLI continue to read and upgrade the downgraded database
    # without reintroducing legacy version-table handling into runtime code.
