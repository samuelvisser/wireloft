"""Persist active download filesystem claims for targeted crash recovery.

Revision ID: e7c91a4d2b60
Revises: 7c2a9e5d4b10
Create Date: 2026-09-14
"""

from alembic import op
import sqlalchemy as sa


revision = "e7c91a4d2b60"
down_revision = "7c2a9e5d4b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_path_claims",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("candidate_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "claim_type IN ('direct_reservation', 'publication_lock')",
            name=op.f("ck_download_path_claims_claim_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_path_claims")),
    )


def downgrade() -> None:
    op.drop_table("download_path_claims")
