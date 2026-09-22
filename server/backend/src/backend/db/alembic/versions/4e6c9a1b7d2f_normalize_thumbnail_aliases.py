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


def _normalize_thumbnail_aliases(bind) -> None:
    shows = _thumbnail_table("shows")
    bind.execute(
        sa.update(shows)
        .where(
            shows.c.thumbnail_landscape_path.is_not(None),
            shows.c.thumbnail_landscape_path == shows.c.thumbnail_portrait_path,
        )
        .values(thumbnail_landscape_path=None)
    )
    bind.execute(
        sa.update(shows)
        .where(
            shows.c.thumbnail_square_path.is_not(None),
            shows.c.thumbnail_square_path == shows.c.thumbnail_portrait_path,
        )
        .values(thumbnail_square_path=None)
    )

    episodes = _thumbnail_table("media_items_episode")
    bind.execute(
        sa.update(episodes)
        .where(
            episodes.c.thumbnail_portrait_path.is_not(None),
            episodes.c.thumbnail_portrait_path
            == episodes.c.thumbnail_landscape_path,
        )
        .values(thumbnail_portrait_path=None)
    )
    bind.execute(
        sa.update(episodes)
        .where(
            episodes.c.thumbnail_square_path.is_not(None),
            episodes.c.thumbnail_square_path
            == episodes.c.thumbnail_landscape_path,
        )
        .values(thumbnail_square_path=None)
    )


def upgrade() -> None:
    _normalize_thumbnail_aliases(op.get_bind())


def downgrade() -> None:
    # One-way cleanup: once a duplicate alias is cleared, it cannot be
    # distinguished from a thumbnail that was genuinely absent beforehand.
    pass
