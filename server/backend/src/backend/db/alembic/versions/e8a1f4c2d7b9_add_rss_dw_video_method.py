"""Add Daily Wire video delivery method to RSS stream profiles.

Revision ID: e8a1f4c2d7b9
Revises: c91e4a6f72d0
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a1f4c2d7b9"
down_revision: Union[str, None] = "c91e4a6f72d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "dw_video_method",
                sa.String(),
                nullable=False,
                server_default="podcasting_2_0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.drop_column("dw_video_method")
