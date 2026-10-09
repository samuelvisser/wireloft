"""Optionally include manual episode downloads in podcast retention.

Revision ID: b6c2e47f918a
Revises: a4e7c19b2d53
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b6c2e47f918a"
down_revision = "a4e7c19b2d53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_profiles_podcast",
        sa.Column(
            "include_manually_downloaded_episodes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("download_profiles_podcast") as batch:
        batch.drop_column("include_manually_downloaded_episodes")
