from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request

from backend.types.stream_profile_types import DEFAULT_RSS_DW_VIDEO_METHOD


RSS_DW_VIDEO_METHOD_QUERY_PARAM = "dwVideoMethod"


def set_rss_feed_dw_video_method(
        feed_url: str,
        *,
        use_dw_stream: bool,
        dw_video_method: str,
) -> str:
    parts = urlsplit(feed_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != RSS_DW_VIDEO_METHOD_QUERY_PARAM
    ]
    if use_dw_stream:
        query.append((RSS_DW_VIDEO_METHOD_QUERY_PARAM, dw_video_method))

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def build_rss_feed_url(
        request: Request,
        *,
        token: str,
        show_slug: str,
        use_dw_stream: bool = False,
        dw_video_method: str = DEFAULT_RSS_DW_VIDEO_METHOD,
) -> str:
    """Build the default feed URL shown for an RSS stream profile."""
    base = str(request.base_url).rstrip("/")
    feed_url = f"{base}/feeds/rss/{token}/{show_slug}.xml"
    return set_rss_feed_dw_video_method(
        feed_url,
        use_dw_stream=use_dw_stream,
        dw_video_method=dw_video_method,
    )
