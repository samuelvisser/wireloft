"""Scope movie-extra identity to its parent movie.

Revision ID: c9f2d8a1b604
Revises: a8e4c1d7f203
"""

from alembic import op
import sqlalchemy as sa


revision = "c9f2d8a1b604"
down_revision = "a8e4c1d7f203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_index("ix_movie_extras_dw_id")
        batch.drop_index("ix_movie_extras_slug")
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=False)
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_dw_id",
            ["movie_id", "dw_id"],
        )
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_slug",
            ["movie_id", "slug"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_dw_id = bind.execute(sa.text(
        "SELECT dw_id FROM movie_extras "
        "WHERE dw_id IS NOT NULL "
        "GROUP BY dw_id HAVING COUNT(*) > 1 LIMIT 1"
    )).scalar_one_or_none()
    duplicate_slug = bind.execute(sa.text(
        "SELECT slug FROM movie_extras "
        "GROUP BY slug HAVING COUNT(*) > 1 LIMIT 1"
    )).scalar_one_or_none()
    if duplicate_dw_id is not None or duplicate_slug is not None:
        raise RuntimeError(
            "Cannot downgrade movie-extra identity constraints because Daily Wire "
            "clips are currently shared by multiple movies. The older schema "
            "requires globally unique movie-extra IDs and slugs."
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_slug", type_="unique")
        batch.drop_constraint("uq_movie_extras_movie_id_dw_id", type_="unique")
        batch.drop_index("ix_movie_extras_slug")
        batch.drop_index("ix_movie_extras_dw_id")
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=True)
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=True)
