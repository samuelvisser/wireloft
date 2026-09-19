"""Add background migration version storage.

Revision ID: e5f1a2c7d903
Revises: 9b1f4e7c2d6a
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f1a2c7d903"
down_revision = "9b1f4e7c2d6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "background_migration_version",
                sa.String(length=32),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("settings") as batch_op:
        batch_op.drop_column("background_migration_version")
