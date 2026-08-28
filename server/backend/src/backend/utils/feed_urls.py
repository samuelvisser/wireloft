from __future__ import annotations

from fastapi import Request


def build_rss_feed_url(request: Request, *, token: str, show_slug: str) -> str:
    """The default, user-editable URL shown for an RSS stream profile.

    Purely informational: it is derived from the host the create/regenerate
    request came in on so it works out of the box, but the actual feed is
    always served from the profile's ``token`` regardless of what this text
    is later edited to.
    """
    base = str(request.base_url).rstrip("/")
    return f"{base}/feeds/rss/{token}/{show_slug}.xml"
