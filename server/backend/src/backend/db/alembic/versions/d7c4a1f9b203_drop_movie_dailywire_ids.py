"""Stop persisting Daily Wire IDs for movies and movie extras.

Revision ID: d7c4a1f9b203
Revises: c9f2d8a1b604
"""

from alembic import op
import sqlalchemy as sa


revision = "d7c4a1f9b203"
down_revision = "c9f2d8a1b604"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate_movie_slug = bind.execute(sa.text(
        "SELECT slug FROM movies GROUP BY slug HAVING COUNT(*) > 1 LIMIT 1"
    )).scalar_one_or_none()
    if duplicate_movie_slug is not None:
        raise RuntimeError(
            "Cannot make movie slugs the canonical identity because duplicate "
            f"movie slug {duplicate_movie_slug!r} already exists"
        )

    # Older movie-page indexing stored the movie PID in this generic source-ID
    # field. It is still useful for stable sources such as TMDB, but a Daily Wire
    # PID must not survive this migration because those identifiers can rotate.
    bind.execute(sa.text(
        "UPDATE movies SET release_date_source_id = NULL "
        "WHERE release_date_source = 'dailywire'"
    ))

    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_dw_id", type_="unique")
        batch.drop_index("ix_movie_extras_dw_id")
        batch.drop_column("dw_id")

    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_dw_id")
        batch.drop_column("dw_id")
        batch.create_index("ix_movies_slug", ["slug"], unique=True)


def downgrade() -> None:
    # Daily Wire IDs are intentionally discarded by the upgrade and cannot be
    # reconstructed safely from persisted data. Recreate nullable columns only;
    # a subsequent live lookup by slug can obtain the current IDs when needed.
    with op.batch_alter_table("movies") as batch:
        batch.drop_index("ix_movies_slug")
        batch.add_column(sa.Column("dw_id", sa.String(), nullable=True))
        batch.create_index("ix_movies_dw_id", ["dw_id"], unique=True)

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("dw_id", sa.String(), nullable=True))
        batch.create_index("ix_movie_extras_dw_id", ["dw_id"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_dw_id",
            ["movie_id", "dw_id"],
        )
