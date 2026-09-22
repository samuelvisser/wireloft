"""Add RSS live episode streaming state.

Revision ID: b6f3c8a1d2e4
Revises: 7c2a9e5d4b10
"""

from alembic import op
import sqlalchemy as sa


revision = "b6f3c8a1d2e4"
down_revision = "7c2a9e5d4b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.add_column(
            sa.Column(
                "stream_live_episodes",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "live_episode_handoff_ids",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.drop_column("live_episode_handoff_ids")
        batch_op.drop_column("stream_live_episodes")
