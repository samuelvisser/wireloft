"""Replace RSS video delivery experiments with output modes.

Revision ID: c1a7e4d9b203
Revises: b6f3c8a1d2e4
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa


revision = "c1a7e4d9b203"
down_revision = "b6f3c8a1d2e4"
branch_labels = None
depends_on = None


_OLD_TO_NEW = {
    "stream_hls_download_m4a": "audio_hls",
    "stream_download_mp4": "mp4",
    "stream_hls_download_mp4": "mp4_hls",
}

_NEW_TO_OLD = {
    "audio_hls": "stream_hls_download_m4a",
    "audio_mp4": "stream_download_mp4",
    "mp4": "stream_download_mp4",
    "mp4_hls": "stream_hls_download_mp4",
}


def _without_legacy_method_query(feed_url: str) -> str:
    parts = urlsplit(feed_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "dwVideoMethod"
    ]
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, dw_video_method, feed_url FROM stream_profiles_rss")
    ).mappings().all()

    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET dw_video_method = :mode, feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "mode": _OLD_TO_NEW.get(row["dw_video_method"], "audio_hls"),
                "feed_url": _without_legacy_method_query(row["feed_url"]),
            },
        )

    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.alter_column(
            "dw_video_method",
            new_column_name="video_output_mode",
            existing_type=sa.String(),
            existing_nullable=False,
            existing_server_default="stream_hls_download_m4a",
            server_default="audio_hls",
        )


def downgrade() -> None:
    connection = op.get_bind()

    with op.batch_alter_table("stream_profiles_rss") as batch_op:
        batch_op.alter_column(
            "video_output_mode",
            new_column_name="dw_video_method",
            existing_type=sa.String(),
            existing_nullable=False,
            existing_server_default="audio_hls",
            server_default="stream_hls_download_m4a",
        )

    rows = connection.execute(
        sa.text("SELECT id, dw_video_method FROM stream_profiles_rss")
    ).mappings().all()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET dw_video_method = :method "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "method": _NEW_TO_OLD.get(
                    row["dw_video_method"],
                    "stream_hls_download_m4a",
                ),
            },
        )
