"""Persist final-redownload intent on episode downloads.

Revision ID: 6d3a9f1c2b7e
Revises: f2a6c93d8b14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "6d3a9f1c2b7e"
down_revision = "f2a6c93d8b14"
branch_labels = None
depends_on = None


_TABLE = "media_downloads_episode"
_SQLITE_BATCH_TABLE = "_alembic_tmp_media_downloads_episode"


def _prepare_interrupted_sqlite_batch(connection) -> None:
    """Recover the scratch table Alembic can leave after a failed SQLite batch."""
    if connection.dialect.name != "sqlite":
        return

    table_names = set(sa.inspect(connection).get_table_names())
    if _SQLITE_BATCH_TABLE not in table_names:
        return

    if _TABLE in table_names:
        # The real table is authoritative. A previous failed batch can leave
        # its create/copy scratch table behind even though Alembic did not
        # advance the revision.
        op.drop_table(_SQLITE_BATCH_TABLE)
    else:
        # If interruption happened after dropping the original table but before
        # the final rename, the scratch table contains the migrated data.
        op.rename_table(_SQLITE_BATCH_TABLE, _TABLE)


def upgrade() -> None:
    connection = op.get_bind()
    _prepare_interrupted_sqlite_batch(connection)

    column_names = {
        column["name"]
        for column in sa.inspect(connection).get_columns(_TABLE)
    }
    if "redownload_when_final" not in column_names:
        # SQLite supports ADD COLUMN directly. Avoid batch mode here so a later
        # backfill failure cannot strand another _alembic_tmp_* table.
        op.add_column(
            _TABLE,
            sa.Column(
                "redownload_when_final",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    connection.execute(
        sa.text(
            "UPDATE media_downloads_episode "
            "SET redownload_when_final = :enabled "
            "WHERE ("
            "downloaded_publish_status = :countdown_status "
            "OR id IN ("
            "SELECT md.id FROM media_downloads AS md "
            "JOIN media_items_episode AS e ON e.id = md.media_item_id "
            "WHERE e.publish_status = :countdown_status"
            ")"
            ") "
            "AND download_profile_id IN ("
            "SELECT id FROM download_profiles_podcast "
            "WHERE download_with_countdown = :enabled "
            "AND redownload_final = :enabled"
            ")"
        ),
        {
            "enabled": True,
            "countdown_status": "published_with_countdown",
        },
    )


def downgrade() -> None:
    with op.batch_alter_table("media_downloads_episode") as batch_op:
        batch_op.drop_column("redownload_when_final")
