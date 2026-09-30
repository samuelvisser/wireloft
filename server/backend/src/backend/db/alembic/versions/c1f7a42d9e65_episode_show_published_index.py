"""Index show episode pagination.

Revision ID: c1f7a42d9e65
Revises: e3a7d92b4c61
"""
from alembic import op


revision = "c1f7a42d9e65"
down_revision = "e3a7d92b4c61"
branch_labels = None
depends_on = None


_INDEX_NAME = "ix_media_items_episode_show_published_id"


def upgrade():
    op.create_index(
        _INDEX_NAME,
        "media_items_episode",
        ["show_id", "published_date", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index(_INDEX_NAME, table_name="media_items_episode")
