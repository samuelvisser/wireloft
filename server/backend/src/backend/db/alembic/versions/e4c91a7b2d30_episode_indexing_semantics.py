"""Add episode indexing semantic columns.

This revision identity was shipped before background-migration version storage was
introduced. Keep it in the graph so databases that already reached
e4c91a7b2d30 can continue upgrading normally.

Revision ID: e4c91a7b2d30
Revises: 9b1f4e7c2d6a
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e4c91a7b2d30"
down_revision = "9b1f4e7c2d6a"
branch_labels = None
depends_on = None


def _column_names(connection, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(connection).get_columns(table_name)
    }


def upgrade() -> None:
    connection = op.get_bind()

    season_columns = _column_names(connection, "seasons")
    missing_season_columns = []
    if "season_type" not in season_columns:
        missing_season_columns.append(
            sa.Column(
                "season_type",
                sa.String(),
                nullable=False,
                server_default="normal",
            )
        )
    if "season_number" not in season_columns:
        missing_season_columns.append(
            sa.Column(
                "season_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
    if missing_season_columns:
        with op.batch_alter_table("seasons") as batch_op:
            for column in missing_season_columns:
                batch_op.add_column(column)

    if "dw_episode_number" not in _column_names(connection, "media_items_episode"):
        with op.batch_alter_table("media_items_episode") as batch_op:
            batch_op.add_column(
                sa.Column("dw_episode_number", sa.String(), nullable=True)
            )


def downgrade() -> None:
    connection = op.get_bind()

    if "dw_episode_number" in _column_names(connection, "media_items_episode"):
        with op.batch_alter_table("media_items_episode") as batch_op:
            batch_op.drop_column("dw_episode_number")

    season_columns = _column_names(connection, "seasons")
    if "season_number" in season_columns or "season_type" in season_columns:
        with op.batch_alter_table("seasons") as batch_op:
            if "season_number" in season_columns:
                batch_op.drop_column("season_number")
            if "season_type" in season_columns:
                batch_op.drop_column("season_type")
