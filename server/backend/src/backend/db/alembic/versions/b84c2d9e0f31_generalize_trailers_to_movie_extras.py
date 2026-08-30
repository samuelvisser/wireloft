"""Generalize trailers to movie extras.

Revision ID: b84c2d9e0f31
Revises: 7f3c2a91d8b4
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b84c2d9e0f31"
down_revision: Union[str, None] = "7f3c2a91d8b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movie_extras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("movie_extra_type", sa.String(), server_default="other", nullable=False),
        sa.Column("dw_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("sharing_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_items.id"],
            name=op.f("fk_movie_extras_id_media_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            name=op.f("fk_movie_extras_movie_id_movies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movie_extras")),
    )
    with op.batch_alter_table("movie_extras", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_movie_extras_dw_id"), ["dw_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_movie_extras_movie_id"), ["movie_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_movie_extras_slug"), ["slug"], unique=True)

    connection = op.get_bind()
    connection.execute(sa.text(
        "INSERT INTO movie_extras "
        "(id, movie_id, movie_extra_type, dw_id, slug, sharing_url) "
        "SELECT id, movie_id, 'trailer', dw_id, slug, sharing_url FROM trailers"
    ))

    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("official_trailer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_movies_official_trailer_id_movie_extras"),
            "movie_extras",
            ["official_trailer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_movies_official_trailer_id"),
            ["official_trailer_id"],
        )

    # Existing WireLoft rows came from the single trailer returned by the movie
    # page. If a database somehow contains more than one, preserve the oldest
    # deterministically as the official trailer.
    connection.execute(sa.text(
        "UPDATE movies SET official_trailer_id = ("
        "SELECT MIN(movie_extras.id) FROM movie_extras "
        "WHERE movie_extras.movie_id = movies.id "
        "AND movie_extras.movie_extra_type = 'trailer'"
        ")"
    ))

    op.create_table(
        "media_downloads_movie_extra",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_downloads.id"],
            name=op.f("fk_media_downloads_movie_extra_id_media_downloads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_downloads_movie_extra")),
    )
    connection.execute(sa.text(
        "INSERT INTO media_downloads_movie_extra (id) "
        "SELECT id FROM media_downloads_trailer"
    ))

    connection.execute(sa.text(
        "UPDATE media_items SET type = 'movie_extra' WHERE type = 'trailer'"
    ))
    connection.execute(sa.text(
        "UPDATE media_downloads SET type = 'movie_extra' WHERE type = 'trailer'"
    ))
    connection.execute(sa.text(
        "UPDATE task_runs SET resource_type = 'MOVIE_EXTRA' WHERE resource_type = 'TRAILER'"
    ))
    connection.execute(sa.text(
        "UPDATE task_schedules SET resource_type = 'MOVIE_EXTRA' WHERE resource_type = 'TRAILER'"
    ))

    op.drop_table("media_downloads_trailer")
    op.drop_table("trailers")


def downgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "trailers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("dw_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("sharing_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_items.id"],
            name=op.f("fk_trailers_id_media_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            name=op.f("fk_trailers_movie_id_movies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trailers")),
    )
    with op.batch_alter_table("trailers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trailers_dw_id"), ["dw_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_trailers_movie_id"), ["movie_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trailers_slug"), ["slug"], unique=True)

    connection.execute(sa.text(
        "INSERT INTO trailers (id, movie_id, dw_id, slug, sharing_url) "
        "SELECT id, movie_id, dw_id, slug, sharing_url FROM movie_extras "
        "WHERE movie_extra_type = 'trailer'"
    ))

    op.create_table(
        "media_downloads_trailer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_downloads.id"],
            name=op.f("fk_media_downloads_trailer_id_media_downloads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_downloads_trailer")),
    )
    connection.execute(sa.text(
        "INSERT INTO media_downloads_trailer (id) "
        "SELECT download.id FROM media_downloads_movie_extra AS download "
        "JOIN media_downloads AS base_download ON base_download.id = download.id "
        "JOIN movie_extras ON movie_extras.id = base_download.media_item_id "
        "WHERE movie_extras.movie_extra_type = 'trailer'"
    ))

    non_trailer_ids = [
        row[0]
        for row in connection.execute(sa.text(
            "SELECT id FROM movie_extras WHERE movie_extra_type != 'trailer'"
        ))
    ]
    if non_trailer_ids:
        placeholders = ", ".join(str(int(value)) for value in non_trailer_ids)
        connection.execute(sa.text(
            f"DELETE FROM media_downloads WHERE media_item_id IN ({placeholders})"
        ))

    connection.execute(sa.text(
        "UPDATE media_items SET type = 'trailer' WHERE id IN (SELECT id FROM trailers)"
    ))
    connection.execute(sa.text(
        "UPDATE media_downloads SET type = 'trailer' "
        "WHERE id IN (SELECT id FROM media_downloads_trailer)"
    ))
    connection.execute(sa.text(
        "UPDATE task_runs SET resource_type = 'TRAILER' WHERE resource_type = 'MOVIE_EXTRA'"
    ))
    connection.execute(sa.text(
        "UPDATE task_schedules SET resource_type = 'TRAILER' WHERE resource_type = 'MOVIE_EXTRA'"
    ))

    op.drop_table("media_downloads_movie_extra")
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_movies_official_trailer_id"), type_="unique")
        batch_op.drop_constraint(
            batch_op.f("fk_movies_official_trailer_id_movie_extras"),
            type_="foreignkey",
        )
        batch_op.drop_column("official_trailer_id")
    op.drop_table("movie_extras")

    if non_trailer_ids:
        placeholders = ", ".join(str(int(value)) for value in non_trailer_ids)
        connection.execute(sa.text(
            f"DELETE FROM media_items WHERE id IN ({placeholders})"
        ))
