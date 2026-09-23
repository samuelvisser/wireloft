"""Normalize duplicate thumbnail aliases.

Revision ID: 4e6c9a1b7d2f
Revises: 7c2a9e5d4b10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "4e6c9a1b7d2f"
down_revision = "7c2a9e5d4b10"
branch_labels = None
depends_on = None


def _thumbnail_table(table_name: str):
    return sa.table(
        table_name,
        sa.column("thumbnail_landscape_path", sa.String()),
        sa.column("thumbnail_portrait_path", sa.String()),
        sa.column("thumbnail_square_path", sa.String()),
    )


_THUMBNAIL_FIELDS = {
    "landscape": "thumbnail_landscape_path",
    "portrait": "thumbnail_portrait_path",
    "square": "thumbnail_square_path",
}


def _normalize_table_thumbnail_aliases(bind, table_name: str, *, default: str) -> None:
    thumbnails = _thumbnail_table(table_name)
    default_column = getattr(thumbnails.c, _THUMBNAIL_FIELDS[default])

    for orientation, field_name in _THUMBNAIL_FIELDS.items():
        if orientation == default:
            continue

        alternate_column = getattr(thumbnails.c, field_name)
        bind.execute(
            sa.update(thumbnails)
            .where(
                alternate_column.is_not(None),
                alternate_column == default_column,
            )
            .values({field_name: None})
        )


def _normalize_thumbnail_aliases(bind) -> None:
    _normalize_table_thumbnail_aliases(bind, "shows", default="portrait")
    _normalize_table_thumbnail_aliases(
        bind,
        "media_items_episode",
        default="landscape",
    )
    _normalize_table_thumbnail_aliases(bind, "media_items_movie", default="portrait")
    _normalize_table_thumbnail_aliases(
        bind,
        "movie_extra_sources",
        default="landscape",
    )


def upgrade() -> None:
    _normalize_thumbnail_aliases(op.get_bind())


def downgrade() -> None:
    # One-way cleanup: once a duplicate alias is cleared, it cannot be
    # distinguished from a thumbnail that was genuinely absent beforehand.
    pass
