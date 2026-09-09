"""Add queued download priority timestamps.

Revision ID: a7c5d9e2f401
Revises: f4d2a7b9c301
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a7c5d9e2f401"
down_revision = "f4d2a7b9c301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_operations",
        sa.Column("prioritized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_task_operations_prioritized_at"),
        "task_operations",
        ["prioritized_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_task_operations_prioritized_at"),
        table_name="task_operations",
    )
    op.drop_column("task_operations", "prioritized_at")
