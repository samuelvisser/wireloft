"""Persist canonical Daily Wire movie-page metadata.

Revision ID: a8e4c1d7f203
Revises: c1f7b9e4d205
"""

from alembic import op
import sqlalchemy as sa


revision = "a8e4c1d7f203"
down_revision = "c1f7b9e4d205"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("movies") as batch:
        batch.add_column(sa.Column("has_video", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("status", sa.String(), nullable=True))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("background", sa.String(), nullable=True))
        batch.add_column(sa.Column("byline", sa.String(), nullable=True))
        batch.add_column(sa.Column("language", sa.String(), nullable=True))
        batch.add_column(sa.Column("origin_country", sa.String(), nullable=True))
        batch.add_column(sa.Column("images", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("cast_and_crew", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("directed_by", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("genres", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("hosts", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("more_like_this", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("production_companies", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("shop_items", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("starring", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("written_by", sa.JSON(), nullable=False, server_default="[]"))

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("available_for", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_column("available_for")

    with op.batch_alter_table("movies") as batch:
        batch.drop_column("written_by")
        batch.drop_column("starring")
        batch.drop_column("shop_items")
        batch.drop_column("production_companies")
        batch.drop_column("more_like_this")
        batch.drop_column("hosts")
        batch.drop_column("genres")
        batch.drop_column("directed_by")
        batch.drop_column("cast_and_crew")
        batch.drop_column("images")
        batch.drop_column("origin_country")
        batch.drop_column("language")
        batch.drop_column("byline")
        batch.drop_column("background")
        batch.drop_column("published_at")
        batch.drop_column("status")
        batch.drop_column("has_video")
