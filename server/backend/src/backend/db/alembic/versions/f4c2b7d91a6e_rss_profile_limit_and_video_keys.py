"""Move RSS limits to profiles and rename Daily Wire video method keys.

Revision ID: f4c2b7d91a6e
Revises: e6f1a4c9d2b7
Create Date: 2026-09-01

"""
from typing import Sequence, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa


revision: str = "f4c2b7d91a6e"
down_revision: Union[str, None] = "e6f1a4c9d2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_QUERY_PARAMETER = "dwVideoMethod"
_OLD_DEFAULT = "podcasting_2_0"
_NEW_DEFAULT = "stream_hls_download_m4a"
_OLD_TO_NEW = {
    "podcasting_2_0": "stream_hls_download_m4a",
    "cached_mp4": "stream_download_mp4",
    "podcasting_2_0_cached_mp4": "stream_hls_download_mp4",
}
_NEW_TO_OLD = {value: key for key, value in _OLD_TO_NEW.items()}


def _set_method(feed_url: str, method: str | None) -> str:
    parts = urlsplit(feed_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != _QUERY_PARAMETER
    ]
    if method is not None:
        query.append((_QUERY_PARAMETER, method))
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def _migrate_methods(mapping: dict[str, str]) -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT rss.id, rss.feed_url, rss.dw_video_method, base.use_dw_stream "
        "FROM stream_profiles_rss AS rss "
        "JOIN stream_profiles AS base ON base.id = rss.id"
    )).mappings()

    for profile in profiles:
        method = mapping.get(profile["dw_video_method"], profile["dw_video_method"])
        feed_url = _set_method(
            profile["feed_url"],
            method if profile["use_dw_stream"] else None,
        )
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET dw_video_method = :method, feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {
                "id": profile["id"],
                "method": method,
                "feed_url": feed_url,
            },
        )


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "max_items",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.alter_column(
            "dw_video_method",
            existing_type=sa.String(),
            server_default=_NEW_DEFAULT,
        )

    _migrate_methods(_OLD_TO_NEW)


def downgrade() -> None:
    _migrate_methods(_NEW_TO_OLD)

    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.alter_column(
            "dw_video_method",
            existing_type=sa.String(),
            server_default=_OLD_DEFAULT,
        )
        batch_op.drop_column("max_items")
