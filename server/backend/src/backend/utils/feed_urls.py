from __future__ import annotations

from fastapi import Request


def build_rss_feed_url(
        request: Request,
        *,
        token: str,
        show_slug: str,
) -> str:
    """Build the stable feed URL shown for an RSS stream profile."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/feeds/rss/{token}/{show_slug}.xml"
