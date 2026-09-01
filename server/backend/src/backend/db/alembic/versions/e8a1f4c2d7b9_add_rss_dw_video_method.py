"""Add Daily Wire video delivery method to RSS stream profiles.

Revision ID: e8a1f4c2d7b9
Revises: c91e4a6f72d0
Create Date: 2026-09-01

"""
from typing import Sequence, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa


revision: str = "e8a1f4c2d7b9"
down_revision: Union[str, None] = "c91e4a6f72d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_QUERY_PARAMETER = "dwVideoMethod"
_DEFAULT_METHOD = "podcasting_2_0"


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


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "dw_video_method",
                sa.String(),
                nullable=False,
                server_default=_DEFAULT_METHOD,
            )
        )

    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT rss.id, rss.feed_url, base.use_dw_stream "
        "FROM stream_profiles_rss AS rss "
        "JOIN stream_profiles AS base ON base.id = rss.id"
    )).mappings()
    for profile in profiles:
        feed_url = _set_method(
            profile["feed_url"],
            _DEFAULT_METHOD if profile["use_dw_stream"] else None,
        )
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {"id": profile["id"], "feed_url": feed_url},
        )


def downgrade() -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, feed_url FROM stream_profiles_rss"
    )).mappings()
    for profile in profiles:
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {
                "id": profile["id"],
                "feed_url": _set_method(profile["feed_url"], None),
            },
        )

    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.drop_column("dw_video_method")
