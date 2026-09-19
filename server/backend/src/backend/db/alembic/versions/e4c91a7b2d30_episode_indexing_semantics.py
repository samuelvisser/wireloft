"""Add episode indexing semantic columns.

Revision ID: e4c91a7b2d30
Revises: e5f1a2c7d903
"""
from alembic import op
import sqlalchemy as sa


revision = "e4c91a7b2d30"
down_revision = "e5f1a2c7d903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("seasons") as batch_op:
        batch_op.add_column(
            sa.Column(
                "season_type",
                sa.String(),
                nullable=False,
                server_default="normal",
            )
        )
        batch_op.add_column(
            sa.Column(
                "season_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    with op.batch_alter_table("media_items_episode") as batch_op:
        batch_op.add_column(
            sa.Column("dw_episode_number", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("media_items_episode") as batch_op:
        batch_op.drop_column("dw_episode_number")

    with op.batch_alter_table("seasons") as batch_op:
        batch_op.drop_column("season_number")
        batch_op.drop_column("season_type")
