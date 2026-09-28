"""Track the upstream format of managed show artwork.

Revision ID: f4c2a8d19e73
Revises: a9d73b8e5f21
"""
from alembic import op
import sqlalchemy as sa

revision = "f4c2a8d19e73"
down_revision = "a9d73b8e5f21"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "show_local_assets",
        sa.Column("source_format", sa.String(16), nullable=True),
    )


def downgrade():
    with op.batch_alter_table("show_local_assets") as batch:
        batch.drop_column("source_format")
