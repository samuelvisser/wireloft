"""Add per-download-profile storage mode.

Revision ID: f8a2d6c4b103
Revises: f4d2a7b9c301
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f8a2d6c4b103"
down_revision = "f4d2a7b9c301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("download_profiles") as batch:
        batch.add_column(
            sa.Column(
                "download_mode",
                sa.String(length=16),
                nullable=False,
                server_default="system",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("download_profiles") as batch:
        batch.drop_column("download_mode")
