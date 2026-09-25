"""Add optional Stream Profile show-title override.

Revision ID: 6d1e8f2a4c73
Revises: d4a7c2e91b63
"""

from alembic import op
import sqlalchemy as sa


revision = "6d1e8f2a4c73"
down_revision = "d4a7c2e91b63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("overwrite_show_title", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.drop_column("overwrite_show_title")
