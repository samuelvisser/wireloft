"""Add embedded metadata and managed NFO options.

Revision ID: b7e1c4a92d6f
Revises: f4c2a8d19e73
"""
from alembic import op
import sqlalchemy as sa


revision = "b7e1c4a92d6f"
down_revision = "f4c2a8d19e73"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "embed_metadata",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "download_nfo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("nfo_path", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_column("nfo_path")

    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("download_nfo")
        batch.drop_column("embed_metadata")
