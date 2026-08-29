"""Create trailer media items

Revision ID: a59b07916fb6
Revises: 828421f64d03
Create Date: 2026-08-29 14:14:55.826429

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = 'a59b07916fb6'
down_revision: Union[str, None] = '828421f64d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trailers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('movie_id', sa.Integer(), nullable=False),
        sa.Column('dw_id', sa.String(), nullable=True),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('sharing_url', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ['id'],
            ['media_items.id'],
            name=op.f('fk_trailers_id_media_items'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['movie_id'],
            ['movies.id'],
            name=op.f('fk_trailers_movie_id_movies'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_trailers')),
    )
    with op.batch_alter_table('trailers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trailers_dw_id'), ['dw_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_trailers_movie_id'), ['movie_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_trailers_slug'), ['slug'], unique=True)

    with op.batch_alter_table('movies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('author_slug', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('logo_image_path', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('available_for', sa.JSON(), server_default='[]', nullable=False))

    _migrate_legacy_trailers()

    with op.batch_alter_table('movies', schema=None) as batch_op:
        batch_op.drop_column('trailer_title')
        batch_op.drop_column('trailer_sharing_url')
        batch_op.drop_column('trailer_slug')
        batch_op.drop_column('trailer_thumbnail_path')


def downgrade() -> None:
    with op.batch_alter_table('movies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trailer_thumbnail_path', sa.VARCHAR(), nullable=True))
        batch_op.add_column(sa.Column('trailer_slug', sa.VARCHAR(), nullable=True))
        batch_op.add_column(sa.Column('trailer_sharing_url', sa.VARCHAR(), nullable=True))
        batch_op.add_column(sa.Column('trailer_title', sa.VARCHAR(), nullable=True))

    trailer_ids = _restore_legacy_trailer_columns()

    with op.batch_alter_table('trailers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_trailers_slug'))
        batch_op.drop_index(batch_op.f('ix_trailers_movie_id'))
        batch_op.drop_index(batch_op.f('ix_trailers_dw_id'))

    op.drop_table('trailers')

    connection = op.get_bind()
    for trailer_id in trailer_ids:
        connection.execute(
            sa.text("DELETE FROM media_items WHERE id = :trailer_id"),
            {"trailer_id": trailer_id},
        )

    with op.batch_alter_table('movies', schema=None) as batch_op:
        batch_op.drop_column('available_for')
        batch_op.drop_column('logo_image_path')
        batch_op.drop_column('author_slug')


def _migrate_legacy_trailers() -> None:
    connection = op.get_bind()
    legacy_trailers = connection.execute(sa.text(
        "SELECT id AS movie_id, slug AS movie_slug, trailer_slug, trailer_title, "
        "trailer_sharing_url, trailer_thumbnail_path "
        "FROM movies "
        "WHERE trailer_slug IS NOT NULL "
        "OR trailer_title IS NOT NULL "
        "OR trailer_sharing_url IS NOT NULL "
        "OR trailer_thumbnail_path IS NOT NULL"
    )).mappings()

    for legacy in legacy_trailers:
        trailer_slug = legacy['trailer_slug'] or (
            f"{legacy['movie_slug'] or 'movie'}-trailer-{legacy['movie_id']}"
        )
        trailer_title = legacy['trailer_title'] or 'Trailer'
        result = connection.execute(sa.text(
            "INSERT INTO media_items "
            "(uuid, type, title, description, downloaded_date, duration, "
            "background_image_path, thumbnail_landscape_path, "
            "thumbnail_portrait_path, thumbnail_square_path) "
            "VALUES (:uuid, 'trailer', :title, NULL, NULL, 0, NULL, :thumbnail, NULL, NULL)"
        ), {
            "uuid": str(uuid4()),
            "title": trailer_title,
            "thumbnail": legacy['trailer_thumbnail_path'],
        })
        trailer_id = result.lastrowid
        if trailer_id is None:
            raise RuntimeError("Could not determine the migrated Trailer media item ID")
        connection.execute(sa.text(
            "INSERT INTO trailers (id, movie_id, dw_id, slug, sharing_url) "
            "VALUES (:id, :movie_id, NULL, :slug, :sharing_url)"
        ), {
            "id": trailer_id,
            "movie_id": legacy['movie_id'],
            "slug": trailer_slug,
            "sharing_url": legacy['trailer_sharing_url'],
        })


def _restore_legacy_trailer_columns() -> list[int]:
    connection = op.get_bind()
    trailers = connection.execute(sa.text(
        "SELECT trailers.id, trailers.movie_id, trailers.slug, trailers.sharing_url, "
        "media_items.title, media_items.thumbnail_landscape_path "
        "FROM trailers "
        "JOIN media_items ON media_items.id = trailers.id "
        "ORDER BY trailers.movie_id, trailers.id"
    )).mappings().all()

    # The old schema can represent only one trailer per movie. Preserve the
    # first trailer deterministically when downgrading from the one-to-many model.
    restored_movie_ids: set[int] = set()
    for trailer in trailers:
        if trailer['movie_id'] in restored_movie_ids:
            continue
        connection.execute(sa.text(
            "UPDATE movies SET "
            "trailer_slug = :slug, trailer_title = :title, "
            "trailer_sharing_url = :sharing_url, "
            "trailer_thumbnail_path = :thumbnail "
            "WHERE id = :movie_id"
        ), {
            "slug": trailer['slug'],
            "title": trailer['title'],
            "sharing_url": trailer['sharing_url'],
            "thumbnail": trailer['thumbnail_landscape_path'],
            "movie_id": trailer['movie_id'],
        })
        restored_movie_ids.add(trailer['movie_id'])

    return [trailer['id'] for trailer in trailers]
