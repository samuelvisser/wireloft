from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse

from .cached_video import get_cached_mp4_path, prepare_cached_mp4
from .service import (
    get_dailywire_stream_url,
    get_media_for_episode,
    get_rss_stream_profile_by_token,
    render_rss_feed,
)
from backend.app import db_session
from backend.types.local_media_profile_types import PreferredFormat
from backend.types.stream_profile_types import RssDwVideoMethod


router = APIRouter(prefix="/feeds", tags=["Feeds"])

_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

_CACHED_MP4_METHODS = {
    RssDwVideoMethod.CACHED_MP4.value,
    RssDwVideoMethod.PODCASTING_2_0_CACHED_MP4.value,
}


def _temporary_stream_redirect(url: str, *, head_only: bool = False) -> Response:
    headers = {"Location": url, **_NO_CACHE_HEADERS}
    if head_only:
        return Response(status_code=302, headers=headers)
    return RedirectResponse(url, status_code=302, headers=_NO_CACHE_HEADERS)


def _rss_response(xml: bytes, *, head_only: bool = False) -> Response:
    return Response(
        content=b"" if head_only else xml,
        media_type="application/rss+xml; charset=utf-8",
        headers={
            **_NO_CACHE_HEADERS,
            "Content-Length": str(len(xml)),
        },
    )


def _cached_mp4_head_response(file_path: Path | None, *, filename: str) -> Response:
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    if file_path is not None:
        headers["Content-Length"] = str(file_path.stat().st_size)

    response = Response(content=b"", media_type="video/mp4", headers=headers)
    if file_path is None:
        del response.headers["content-length"]
    return response


@router.api_route("/rss/{token}/{show_slug}.xml", methods=["GET", "HEAD"])
def rss_feed(token: str, show_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        xml = render_rss_feed(s, request, profile)
    return _rss_response(xml, head_only=request.method == "HEAD")


@router.api_route("/rss/{token}/episodes/{episode_slug}", methods=["GET", "HEAD"])
def rss_feed_episode_media(token: str, episode_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        episode, download = get_media_for_episode(s, profile, episode_slug)
        if download is None:
            return _temporary_stream_redirect(
                get_dailywire_stream_url(profile, episode),
                head_only=request.method == "HEAD",
            )
        file_path = Path(download.file_path)

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not available")

    return FileResponse(
        file_path,
        filename=file_path.name,
        content_disposition_type="inline",
    )


@router.api_route("/rss/{token}/episodes/{episode_slug}/audio", methods=["GET", "HEAD"])
def rss_feed_episode_audio(token: str, episode_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        if not profile.use_dw_stream:
            raise HTTPException(
                status_code=404,
                detail="Daily Wire streaming is disabled for this feed",
            )
        episode, _ = get_media_for_episode(s, profile, episode_slug)
        return _temporary_stream_redirect(
            get_dailywire_stream_url(
                profile,
                episode,
                media_kind="audio",
            ),
            head_only=request.method == "HEAD",
        )


@router.api_route("/rss/{token}/episodes/{episode_slug}/video.mp4", methods=["GET", "HEAD"])
def rss_feed_episode_video_mp4(token: str, episode_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        if (
            not profile.use_dw_stream
            or profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
            or profile.dw_video_method not in _CACHED_MP4_METHODS
        ):
            raise HTTPException(status_code=404, detail="Cached video is not enabled for this feed")

        episode, download = get_media_for_episode(s, profile, episode_slug)
        if download is not None:
            raise HTTPException(status_code=404, detail="Episode uses downloaded media")

        episode_uuid = episode.uuid
        filename = f"{episode.slug}.mp4"
        cached_file = get_cached_mp4_path(episode_uuid)
        if request.method == "HEAD":
            return _cached_mp4_head_response(cached_file, filename=filename)

        if cached_file is None:
            source_url = get_dailywire_stream_url(
                profile,
                episode,
                media_kind="video",
            )

    if cached_file is None:
        cached_file = prepare_cached_mp4(
            source_url,
            episode_uuid=episode_uuid,
        )
    else:
        try:
            cached_file.touch()
        except OSError:
            pass

    return FileResponse(
        cached_file,
        filename=filename,
        content_disposition_type="inline",
        media_type="video/mp4",
    )
