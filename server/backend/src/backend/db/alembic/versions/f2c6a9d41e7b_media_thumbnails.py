"""Add media thumbnail handling settings and sidecar tracking.

Revision ID: f2c6a9d41e7b
Revises: d8b4a1f6c203
"""

from alembic import op
import sqlalchemy as sa


revision = "f2c6a9d41e7b"
down_revision = "d8b4a1f6c203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("local_media_profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "thumbnail_mode",
                sa.String(length=24),
                nullable=False,
                server_default="system",
            )
        )

    with op.batch_alter_table("media_downloads") as batch_op:
        batch_op.add_column(sa.Column("thumbnail_path", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("media_downloads") as batch_op:
        batch_op.drop_column("thumbnail_path")

    with op.batch_alter_table("local_media_profiles") as batch_op:
        batch_op.drop_column("thumbnail_mode")
