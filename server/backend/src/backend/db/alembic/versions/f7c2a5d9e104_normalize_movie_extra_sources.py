"""Normalize shared movie-extra sources by immutable slug.

Revision ID: f7c2a5d9e104
Revises: d7c4a1f9b203
"""

from alembic import op
import sqlalchemy as sa


revision = "f7c2a5d9e104"
down_revision = "d7c4a1f9b203"
branch_labels = None
depends_on = None


def _official_trailer_links(bind) -> list[tuple[int, int]]:
    """Snapshot links that SQLite may null while batch-rebuilding movie_extras."""
    return [
        (int(row.id), int(row.official_trailer_id))
        for row in bind.execute(sa.text(
            "SELECT id, official_trailer_id FROM movies "
            "WHERE official_trailer_id IS NOT NULL"
        ))
    ]


def _restore_official_trailer_links(bind, links: list[tuple[int, int]]) -> None:
    for movie_id, movie_extra_id in links:
        bind.execute(sa.text(
            "UPDATE movies SET official_trailer_id = :movie_extra_id WHERE id = :movie_id"
        ), {
            "movie_id": movie_id,
            "movie_extra_id": movie_extra_id,
        })


def upgrade() -> None:
    bind = op.get_bind()
    official_trailer_links = _official_trailer_links(bind)

    op.create_table(
        "movie_extra_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movie_extra_sources")),
        sa.UniqueConstraint("slug", name="uq_movie_extra_sources_slug"),
    )

    # Existing MovieExtra rows already represent parent-specific placements.
    # Deduplicate only their immutable upstream identity, preserving every media
    # item ID so media_downloads and task resources remain valid as-is.
    bind.execute(sa.text(
        "INSERT INTO movie_extra_sources (slug) "
        "SELECT DISTINCT slug FROM movie_extras"
    ))

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("source_id", sa.Integer(), nullable=True))

    bind.execute(sa.text(
        "UPDATE movie_extras SET source_id = ("
        "SELECT movie_extra_sources.id FROM movie_extra_sources "
        "WHERE movie_extra_sources.slug = movie_extras.slug"
        ")"
    ))

    unresolved = bind.execute(sa.text(
        "SELECT COUNT(*) FROM movie_extras WHERE source_id IS NULL"
    )).scalar_one()
    if unresolved:
        raise RuntimeError(
            "Could not resolve every existing movie extra to its immutable slug source"
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.drop_constraint("uq_movie_extras_movie_id_slug", type_="unique")
        batch.drop_index("ix_movie_extras_slug")
        batch.create_index("ix_movie_extras_source_id", ["source_id"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_source_id",
            ["movie_id", "source_id"],
        )
        batch.create_foreign_key(
            "fk_movie_extras_source_id_movie_extra_sources",
            "movie_extra_sources",
            ["source_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.alter_column(
            "source_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch.drop_column("slug")

    _restore_official_trailer_links(bind, official_trailer_links)


def downgrade() -> None:
    bind = op.get_bind()
    official_trailer_links = _official_trailer_links(bind)

    with op.batch_alter_table("movie_extras") as batch:
        batch.add_column(sa.Column("slug", sa.String(), nullable=True))

    bind.execute(sa.text(
        "UPDATE movie_extras SET slug = ("
        "SELECT movie_extra_sources.slug FROM movie_extra_sources "
        "WHERE movie_extra_sources.id = movie_extras.source_id"
        ")"
    ))

    unresolved = bind.execute(sa.text(
        "SELECT COUNT(*) FROM movie_extras WHERE slug IS NULL"
    )).scalar_one()
    if unresolved:
        raise RuntimeError(
            "Cannot downgrade movie-extra sources because one or more source slugs are missing"
        )

    with op.batch_alter_table("movie_extras") as batch:
        batch.alter_column(
            "slug",
            existing_type=sa.String(),
            nullable=False,
        )
        batch.drop_constraint(
            "fk_movie_extras_source_id_movie_extra_sources",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "uq_movie_extras_movie_id_source_id",
            type_="unique",
        )
        batch.drop_index("ix_movie_extras_source_id")
        batch.drop_column("source_id")
        batch.create_index("ix_movie_extras_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_movie_extras_movie_id_slug",
            ["movie_id", "slug"],
        )

    _restore_official_trailer_links(bind, official_trailer_links)
    op.drop_table("movie_extra_sources")
