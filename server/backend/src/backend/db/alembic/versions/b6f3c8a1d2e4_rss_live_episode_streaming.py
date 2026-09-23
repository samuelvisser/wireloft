"""Add RSS live episode streaming state.

Revision ID: b6f3c8a1d2e4
Revises: 4e6c9a1b7d2f
"""

from alembic import op
import sqlalchemy as sa


revision = "b6f3c8a1d2e4"
down_revision = "4e6c9a1b7d2f"
branch_labels = None
depends_on = None


_HLS_VIDEO_METHODS = (
    "stream_hls_download_m4a",
    "stream_hls_download_mp4",
)


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.add_column(
            sa.Column(
                "stream_live_episodes",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
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

    # HLS video profiles using Daily Wire already exposed LIVE episodes before
    # this setting existed. Keep those existing profiles behaviorally unchanged;
    # newly created profiles still use the explicit opt-in default.
    connection = op.get_bind()
    rss = sa.table(
        "stream_profiles_rss",
        sa.column("id", sa.Integer()),
        sa.column("dw_video_method", sa.String()),
        sa.column("stream_live_episodes", sa.Boolean()),
    )
    base = sa.table(
        "stream_profiles",
        sa.column("id", sa.Integer()),
        sa.column("use_dw_stream", sa.Boolean()),
        sa.column("preferred_format", sa.String()),
    )
    existing_hls_profiles = (
        sa.select(rss.c.id)
        .select_from(rss.join(base, base.c.id == rss.c.id))
        .where(
            base.c.use_dw_stream.is_(True),
            base.c.preferred_format != "format_audio_only",
            rss.c.dw_video_method.in_(_HLS_VIDEO_METHODS),
        )
    )
    connection.execute(
        rss.update()
        .where(rss.c.id.in_(existing_hls_profiles))
        .values(stream_live_episodes=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.drop_column("live_episode_handoff_ids")
        batch_op.drop_column("stream_live_episodes")
