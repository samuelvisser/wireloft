"""Add episode metadata finality state.

Revision ID: c8d4e2f1a7b9
Revises: b7c3f1a9d2e4
Create Date: 2026-09-02

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d4e2f1a7b9"
down_revision: Union[str, None] = "b7c3f1a9d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing episodes are considered settled. Newly indexed episodes explicitly
    # opt into metadata monitoring when they are recent enough to need it.
    op.add_column(
        "episodes",
        sa.Column(
            "metadata_is_final",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("episodes", "metadata_is_final")
