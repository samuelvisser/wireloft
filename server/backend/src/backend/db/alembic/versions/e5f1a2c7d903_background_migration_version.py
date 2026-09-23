"""Add background migration version storage.

Revision ID: e5f1a2c7d903
Revises: e4c91a7b2d30
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f1a2c7d903"
down_revision = "e4c91a7b2d30"
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
