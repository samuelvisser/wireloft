"""Remove promotional movie metadata from persisted movies.

Revision ID: c5a9e2f7b104
Revises: b3e6d1f8c704
"""

from alembic import op
import sqlalchemy as sa


revision = "c5a9e2f7b104"
down_revision = "b3e6d1f8c704"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These fields are promotional Daily Wire payload data rather than metadata
    # WireLoft needs to manage or download a movie.
    op.drop_column("movies", "shop_items")
    op.drop_column("movies", "more_like_this")


def downgrade() -> None:
    op.add_column(
        "movies",
        sa.Column("more_like_this", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "movies",
        sa.Column("shop_items", sa.JSON(), nullable=False, server_default="[]"),
    )
