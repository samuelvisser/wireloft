"""Rename the RSS exact-match preference.

Revision ID: 3f7b6a2c9d10
Revises: 5a9c2e7d4b10
"""

from alembic import op
import sqlalchemy as sa


revision = "3f7b6a2c9d10"
down_revision = "5a9c2e7d4b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.alter_column(
            "require_exact_match",
            new_column_name="prefer_exact_match",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("stream_profiles") as batch_op:
        batch_op.alter_column(
            "prefer_exact_match",
            new_column_name="require_exact_match",
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )
