"""Add fixed podcast download starting date.

Revision ID: d8b4a1f6c203
Revises: f4d2a7b9c301
"""

from alembic import op
import sqlalchemy as sa


revision = "d8b4a1f6c203"
down_revision = "f4d2a7b9c301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("download_profiles_podcast") as batch:
        batch.add_column(
            sa.Column("download_starting_from", sa.Date(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("download_profiles_podcast") as batch:
        batch.drop_column("download_starting_from")
