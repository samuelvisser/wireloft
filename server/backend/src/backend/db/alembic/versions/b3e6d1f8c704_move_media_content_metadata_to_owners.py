"""Move reusable media content metadata to concrete owners.

Revision ID: b3e6d1f8c704
Revises: e8d1c4b7a205
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b3e6d1f8c704"
down_revision = "e8d1c4b7a205"
branch_labels = None
depends_on = None


_CONTENT_FIELDS = (
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
)


def _add_content_columns(table_name: str) -> None:
    # Defaults let SQLite add NOT NULL columns without rebuilding tables that are
    # referenced by other WireLoft tables. Application/API validation still
    # supplies real titles; these defaults only make the structural mixin portable.
    op.add_column(
        table_name,
        sa.Column("title", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        table_name,
        sa.Column("description", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("duration", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        table_name,
        sa.Column("background_image_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_landscape_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_portrait_path", sa.String(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("thumbnail_square_path", sa.String(), nullable=True),
    )


def _copy_content_metadata(
    bind,
    *,
    source_table_name: str,
    target_table_name: str,
) -> None:
    metadata = sa.MetaData()
    source = sa.Table(source_table_name, metadata, autoload_with=bind)
    target = sa.Table(target_table_name, metadata, autoload_with=bind)

    values = {
        field: (
            sa.select(source.c[field])
            .where(source.c.id == target.c.id)
            .scalar_subquery()
        )
        for field in _CONTENT_FIELDS
    }
    bind.execute(sa.update(target).values(**values))


def upgrade() -> None:
    bind = op.get_bind()

    _add_content_columns("episodes")
    _add_content_columns("movies")

    # Every existing Episode/Movie media item has a one-to-one joined-inheritance
    # row with the same ID, so metadata moves without rewriting any identities or
    # foreign keys. MovieExtra metadata already lives on movie_extra_sources.
    _copy_content_metadata(
        bind,
        source_table_name="media_items",
        target_table_name="episodes",
    )
    _copy_content_metadata(
        bind,
        source_table_name="media_items",
        target_table_name="movies",
    )

    # Modern SQLite supports native DROP COLUMN. Use it directly rather than an
    # Alembic batch rebuild: media_items is the parent of every concrete media
    # table and of media_downloads, so rebuilding it would unnecessarily disturb
    # those otherwise unchanged foreign-key relationships.
    for field in reversed(_CONTENT_FIELDS):
        op.drop_column("media_items", field)


def downgrade() -> None:
    bind = op.get_bind()

    # Recreate the previous joined-inheritance base schema. Defaults are required
    # for portable in-place addition of the two NOT NULL fields.
    _add_content_columns("media_items")

    metadata = sa.MetaData()
    media_items = sa.Table("media_items", metadata, autoload_with=bind)
    episodes = sa.Table("episodes", metadata, autoload_with=bind)
    movies = sa.Table("movies", metadata, autoload_with=bind)

    for concrete in (episodes, movies):
        bind.execute(
            sa.update(media_items)
            .where(media_items.c.id.in_(sa.select(concrete.c.id)))
            .values(**{
                field: (
                    sa.select(concrete.c[field])
                    .where(concrete.c.id == media_items.c.id)
                    .scalar_subquery()
                )
                for field in _CONTENT_FIELDS
            })
        )

    # e8d1c4b7a205 intentionally kept MovieExtra's inherited base columns as
    # neutral placeholders because authoritative values already lived on the
    # source. Restoring those placeholders recreates that exact data contract.
    bind.execute(
        sa.update(media_items)
        .where(media_items.c.type == "movie_extra")
        .values(
            title="",
            description=None,
            duration=0.0,
            background_image_path=None,
            thumbnail_landscape_path=None,
            thumbnail_portrait_path=None,
            thumbnail_square_path=None,
        )
    )

    for field in reversed(_CONTENT_FIELDS):
        op.drop_column("movies", field)
        op.drop_column("episodes", field)
