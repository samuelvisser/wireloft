"""Make subtitle defaults depend on Local Media Profile type and show scope.

Revision ID: c4e93f1a2b6d
Revises: b7d31f5a2c90

Canonical profile choices remain unchanged. Only the removed "system" mode is
migrated to a scope-specific value. The preceding migration establishes new
defaults for installations that did not already have a subtitle_mode column.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c4e93f1a2b6d"
down_revision = "b7d31f5a2c90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Resolve stored "system" modes now that subtitles are profile-only.
    op.execute(sa.text("""
        UPDATE local_media_profiles
        SET subtitle_mode = 'sidecar'
        WHERE subtitle_mode = 'system'
          AND (
            type = 'movie'
            OR id IN (
                SELECT id FROM local_media_profiles_show
                WHERE show_scope IN ('series', 'both')
            )
          )
    """))
    op.execute(sa.text("""
        UPDATE local_media_profiles
        SET subtitle_mode = 'no_subtitles'
        WHERE subtitle_mode = 'system'
    """))

    # Keep every explicit no_subtitles/embed/sidecar choice unchanged. Without
    # an explicitness marker, a saved choice must not be treated as a default.

    with op.batch_alter_table("local_media_profiles") as batch:
        batch.alter_column(
            "subtitle_mode",
            existing_type=sa.String(length=24),
            existing_nullable=False,
            server_default="sidecar",
        )


def downgrade() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.alter_column(
            "subtitle_mode",
            existing_type=sa.String(length=24),
            existing_nullable=False,
            server_default="no_subtitles",
        )
