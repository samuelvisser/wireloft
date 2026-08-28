from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

from .service import get_download_for_episode, get_rss_stream_profile_by_token, render_rss_feed
from backend.app import db_session

# Deliberately mounted outside the /api prefix (see backend.app.create_app) so
# it is never subject to the auth middleware: podcast apps need a feed URL
# that keeps working with no session/cookie, even when local auth is on. The
# per-profile token in the path is what keeps it from being guessable.
router = APIRouter(prefix="/feeds", tags=["Feeds"])


@router.get("/rss/{token}/{show_slug}.xml")
def rss_feed(token: str, show_slug: str, request: Request):
    """
    Serve a show's RSS feed for the RSS stream profile identified by ``token``.

    ``show_slug`` is only there to make the URL readable; it is not checked.
    """
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        xml = render_rss_feed(s, request, profile)
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/rss/{token}/episodes/{episode_slug}")
def rss_feed_episode_media(token: str, episode_slug: str):
    """
    Serve the downloaded media file backing one feed item.

    Supports HTTP Range requests (via FileResponse) so podcast apps can seek
    and resume downloads.
    """
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        download = get_download_for_episode(s, profile, episode_slug)
        file_path = Path(download.file_path)

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not available")

    return FileResponse(file_path, filename=file_path.name, content_disposition_type="inline")
