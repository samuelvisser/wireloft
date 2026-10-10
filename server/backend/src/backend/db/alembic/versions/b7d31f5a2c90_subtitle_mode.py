"""Add Local Media Profile subtitle handling.

Revision ID: b7d31f5a2c90
Revises: a4e7c19b2d53
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b7d31f5a2c90"
down_revision = "a4e7c19b2d53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "local_media_profiles",
        sa.Column("subtitle_mode", sa.String(length=24), nullable=False, server_default="no_subtitles"),
    )
    # Existing movie profiles should acquire subtitles on their next download.
    op.execute(
        sa.text("UPDATE local_media_profiles SET subtitle_mode = 'sidecar' WHERE type = 'movie'")
    )
    # Before subtitle handling existed, no profile could have selected a mode.
    # Assign the new defaults based on the existing Show Local Media Profile scope.
    op.execute(sa.text("""
        UPDATE local_media_profiles
        SET subtitle_mode = 'sidecar'
        WHERE type = 'show' AND id IN (
            SELECT id FROM local_media_profiles_show
            WHERE show_scope IN ('series', 'both')
        )
    """))


def downgrade() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("subtitle_mode")
