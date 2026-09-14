"""Scope season slugs to their show.

Revision ID: f4d2a7b9c301
Revises: e1c7a4b9d302
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f4d2a7b9c301"
down_revision = "e1c7a4b9d302"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("seasons") as batch:
        batch.drop_index("ix_seasons_slug")
        batch.create_index("ix_seasons_slug", ["slug"], unique=False)
        batch.create_unique_constraint(
            "uq_season_show_slug",
            ["show_id", "slug"],
        )


def downgrade() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT slug, COUNT(*) AS season_count "
            "FROM seasons "
            "GROUP BY slug "
            "HAVING COUNT(*) > 1 "
            "LIMIT 1"
        )
    ).mappings().first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot restore globally unique season slugs while multiple shows use "
            f"season slug '{duplicate['slug']}' ({duplicate['season_count']} rows)."
        )

    with op.batch_alter_table("seasons") as batch:
        batch.drop_constraint("uq_season_show_slug", type_="unique")
        batch.drop_index("ix_seasons_slug")
        batch.create_index("ix_seasons_slug", ["slug"], unique=True)
