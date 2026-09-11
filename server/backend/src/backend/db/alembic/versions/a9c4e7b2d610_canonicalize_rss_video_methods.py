"""Canonicalize RSS video method values.

Revision ID: a9c4e7b2d610
Revises: f4d2a7b9c301
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa


revision = "a9c4e7b2d610"
down_revision = "f4d2a7b9c301"
branch_labels = None
depends_on = None


_DW_VIDEO_METHOD_QUERY_PARAMETER = "dwVideoMethod"
_LEGACY_TO_CANONICAL_METHOD = {
    "podcasting_2_0": "stream_hls_download_m4a",
    "cached_mp4": "stream_download_mp4",
    "podcasting_2_0_cached_mp4": "stream_hls_download_mp4",
}


def _canonicalize_feed_url(feed_url: str) -> str:
    parts = urlsplit(feed_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    changed = False
    updated_query: list[tuple[str, str]] = []

    for key, value in query:
        if key == _DW_VIDEO_METHOD_QUERY_PARAMETER:
            canonical_value = _LEGACY_TO_CANONICAL_METHOD.get(value)
            if canonical_value is not None:
                value = canonical_value
                changed = True
        updated_query.append((key, value))

    if not changed:
        return feed_url

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(updated_query),
        parts.fragment,
    ))


def upgrade() -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, dw_video_method, feed_url FROM stream_profiles_rss"
    )).mappings().all()

    for profile in profiles:
        current_method = profile["dw_video_method"]
        canonical_method = _LEGACY_TO_CANONICAL_METHOD.get(
            current_method,
            current_method,
        )
        current_feed_url = profile["feed_url"]
        canonical_feed_url = _canonicalize_feed_url(current_feed_url)

        if (
            canonical_method == current_method
            and canonical_feed_url == current_feed_url
        ):
            continue

        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET dw_video_method = :dw_video_method, feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {
                "id": profile["id"],
                "dw_video_method": canonical_method,
                "feed_url": canonical_feed_url,
            },
        )


def downgrade() -> None:
    # This is intentionally a one-way cleanup. Reintroducing retired identifiers
    # would make a downgraded database incompatible with current application code.
    pass
