"""Persist redownload-after-delay intent on episode downloads.

Revision ID: a4e7c19b2d53
Revises: 6d3a9f1c2b7e
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a4e7c19b2d53"
down_revision = "6d3a9f1c2b7e"
branch_labels = None
depends_on = None


_TABLE = "media_downloads_episode"


def upgrade() -> None:
    connection = op.get_bind()
    column_names = {
        column["name"]
        for column in sa.inspect(connection).get_columns(_TABLE)
    }
    if "redownload_when_delay_passed" not in column_names:
        op.add_column(
            _TABLE,
            sa.Column(
                "redownload_when_delay_passed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_column("redownload_when_delay_passed")
