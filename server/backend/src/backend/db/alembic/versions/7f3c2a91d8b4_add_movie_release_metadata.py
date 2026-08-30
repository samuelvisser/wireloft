"""Add movie release metadata

Revision ID: 7f3c2a91d8b4
Revises: d2c4a7318b90
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f3c2a91d8b4"
down_revision: Union[str, None] = "d2c4a7318b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("release_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("release_date_source", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("release_date_source_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column(
            "release_date_lookup_status",
            sa.String(),
            server_default="pending",
            nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "release_date_lookup_attempted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ))
        batch_op.add_column(sa.Column("release_date_lookup_error", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.drop_column("release_date_lookup_error")
        batch_op.drop_column("release_date_lookup_attempted_at")
        batch_op.drop_column("release_date_lookup_status")
        batch_op.drop_column("release_date_source_id")
        batch_op.drop_column("release_date_source")
        batch_op.drop_column("release_date")
