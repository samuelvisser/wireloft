"""Add show scope to Show Local Media Profiles.

Revision ID: e3a1b5c7d902
Revises: b7e2c4d9a601
"""

from alembic import op
import sqlalchemy as sa


revision = "e3a1b5c7d902"
down_revision = "b7e2c4d9a601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "local_media_profiles_show",
        sa.Column(
            "show_scope",
            sa.String(),
            server_default="both",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("local_media_profiles_show", "show_scope")
