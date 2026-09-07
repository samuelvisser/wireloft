"""Canonicalize episode lifecycle metadata keys.

Revision ID: a4d7c2e9f610
Revises: e6a9c1f4b203
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a4d7c2e9f610"
down_revision = "e6a9c1f4b203"
branch_labels = None
depends_on = None

_METADATA_RENAMES = {
    "dw_processing.reason": "no_usable_media.reason",
    "dw_processing.since": "no_usable_media.since",
}


def _migrate_metadata_key(connection, old: str, new: str) -> None:
    """Move one episode metadata key to its canonical name without duplicates."""
    rows = list(connection.execute(
        sa.text(
            "SELECT id,parent_id FROM metadata "
            "WHERE parent_table='episodes' AND key=:old"
        ),
        {"old": old},
    ))

    for legacy_id, episode_id in rows:
        canonical_id = connection.execute(
            sa.text(
                "SELECT id FROM metadata "
                "WHERE parent_table='episodes' AND parent_id=:episode_id AND key=:new"
            ),
            {"episode_id": episode_id, "new": new},
        ).scalar_one_or_none()

        if canonical_id is None:
            connection.execute(
                sa.text("UPDATE metadata SET key=:new WHERE id=:legacy_id"),
                {"new": new, "legacy_id": legacy_id},
            )
        else:
            # Canonical data already exists, so it wins and the obsolete row can go.
            connection.execute(
                sa.text("DELETE FROM metadata WHERE id=:legacy_id"),
                {"legacy_id": legacy_id},
            )


def upgrade() -> None:
    connection = op.get_bind()
    for old, new in _METADATA_RENAMES.items():
        _migrate_metadata_key(connection, old, new)


def downgrade() -> None:
    connection = op.get_bind()
    for old, new in reversed(tuple(_METADATA_RENAMES.items())):
        _migrate_metadata_key(connection, new, old)
