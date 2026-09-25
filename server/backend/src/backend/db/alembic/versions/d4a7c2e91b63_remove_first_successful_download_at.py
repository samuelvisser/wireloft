"""Remove obsolete first-successful-download tracking.

Revision ID: d4a7c2e91b63
Revises: c80e4d9a6b21
"""

from alembic import op
import sqlalchemy as sa


revision = "d4a7c2e91b63"
down_revision = "c80e4d9a6b21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier revisions of the feature branch created this column. It is not
    # part of the final schema, but branch databases may already have applied
    # that prerelease migration.
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("media_downloads")
    }
    if "first_successful_download_at" in columns:
        with op.batch_alter_table("media_downloads") as batch_op:
            batch_op.drop_column("first_successful_download_at")


def downgrade() -> None:
    # The preceding canonical revision no longer contains this obsolete column.
    pass
