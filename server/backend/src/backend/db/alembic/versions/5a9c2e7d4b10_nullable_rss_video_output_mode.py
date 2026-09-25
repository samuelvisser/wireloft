"""Allow RSS video output mode to be null for audio-only profiles.

Revision ID: 5a9c2e7d4b10
Revises: c1a7e4d9b203
"""

from alembic import op
import sqlalchemy as sa


revision = "5a9c2e7d4b10"
down_revision = "c1a7e4d9b203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.alter_column(
            "video_output_mode",
            existing_type=sa.String(),
            existing_nullable=False,
            existing_server_default="audio_hls",
            nullable=True,
            server_default=None,
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE stream_profiles_rss "
            "SET video_output_mode = NULL "
            "WHERE id IN ("
            "SELECT rss.id "
            "FROM stream_profiles_rss AS rss "
            "JOIN stream_profiles AS base ON base.id = rss.id "
            "WHERE base.preferred_format = :audio_only"
            ")"
        ),
        {"audio_only": "format_audio_only"},
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE stream_profiles_rss "
            "SET video_output_mode = :default_mode "
            "WHERE video_output_mode IS NULL"
        ),
        {"default_mode": "audio_hls"},
    )

    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.alter_column(
            "video_output_mode",
            existing_type=sa.String(),
            existing_nullable=True,
            nullable=False,
            server_default="audio_hls",
        )
