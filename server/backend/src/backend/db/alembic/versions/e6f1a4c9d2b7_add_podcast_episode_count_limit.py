"""Add podcast episode count download limit

Revision ID: e6f1a4c9d2b7
Revises: c91e4a6f72d0
Create Date: 2026-09-01 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f1a4c9d2b7"
down_revision: Union[str, None] = "c91e4a6f72d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("download_profiles_podcast", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "download_episode_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ))


def downgrade() -> None:
    with op.batch_alter_table("download_profiles_podcast", schema=None) as batch_op:
        batch_op.drop_column("download_episode_count")
