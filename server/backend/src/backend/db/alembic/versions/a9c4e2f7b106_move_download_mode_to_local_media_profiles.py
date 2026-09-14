"""Add configurable temporary download storage.

Revision ID: a9c4e2f7b106
Revises: f4d2a7b9c301
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a9c4e2f7b106"
down_revision = "f4d2a7b9c301"
branch_labels = None
depends_on = None

_NEW_PROFILE_INDEX = "uq_local_media_profiles_type_template_format_mode"


def upgrade() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "download_mode",
                sa.String(length=16),
                nullable=False,
                server_default="system",
            )
        )
        # Keep the existing uniqueness guarantee on
        # (type, output_template, preferred_format). Download behavior is an
        # execution preference, not part of a Local Media Profile's identity.
        # The mode-aware index remains as a redundant compatibility index for
        # this unmerged migration revision; the stricter legacy index is what
        # defines the actual uniqueness behavior.
        batch.create_index(
            _NEW_PROFILE_INDEX,
            ["type", "output_template", "preferred_format", "download_mode"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_index(_NEW_PROFILE_INDEX)
        batch.drop_column("download_mode")
