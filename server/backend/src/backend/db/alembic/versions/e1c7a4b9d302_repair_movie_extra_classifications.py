"""Repair persisted movie-extra trailer classifications.

Revision ID: e1c7a4b9d302
Revises: d8f3a1c6b205
"""

from alembic import op
import sqlalchemy as sa


revision = "e1c7a4b9d302"
down_revision = "d8f3a1c6b205"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make the explicit official-trailer relationship authoritative once."""
    bind = op.get_bind()
    bind.execute(sa.text(
        """
        UPDATE media_items_movie_extra
        SET movie_extra_type = 'trailer'
        WHERE id IN (
            SELECT official_trailer_id
            FROM media_items_movie
            WHERE official_trailer_id IS NOT NULL
        )
        """
    ))


def downgrade() -> None:
    # The previous classifications cannot be reconstructed after correcting them.
    # Keeping the corrected value is safer than inventing stale data on downgrade.
    pass
