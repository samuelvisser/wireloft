from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse

from .cached_video import get_cached_mp4_path, prepare_cached_mp4
from .hls_experiments import (
    HLS_APPLE_MPEGURL,
    HLS_GENERIC_MPEGURL,
    HLS_X_MPEGURL,
    prepared_hls_resource_response,
    transparent_hls_proxy_response,
)
from .hls_probe_experiments import (
    get_prefetched_hls_url,
    prefetched_hls_manifest_response,
    remember_prefetched_hls_url,
    synthetic_hls_head_response,
)
from .service import (
    get_dailywire_stream_url,
    get_media_for_episode,
    get_rss_stream_profile_by_token,
    render_rss_feed,
)
from backend.app import db_session
from backend.types.local_media_profile_types import PreferredFormat
from backend.types.stream_profile_types import RssDwVideoMethod


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feeds", tags=["Feeds"])

_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
_HLS_REDIRECT_HEADERS = {
    "Content-Type": HLS_X_MPEGURL,
    "Content-Disposition": 'inline; filename="video.m3u8"',
}

_CACHED_MP4_METHODS = {
    RssDwVideoMethod.STREAM_DOWNLOAD_MP4.value,
    RssDwVideoMethod.STREAM_HLS_DOWNLOAD_MP4.value,
}


def _temporary_stream_redirect(
        url: str,
        *,
        head_only: bool = False,
        status_code: int = 302,
        extra_headers: dict[str, str] | None = None,
) -> Response:
    headers = {"Location": url, **_NO_CACHE_HEADERS}
    if extra_headers:
        headers.update(extra_headers)
    if head_only:
        return Response(status_code=status_code, headers=headers)
    return RedirectResponse(
        url,
        status_code=status_code,
        headers=headers,
    )


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


def _resolve_remote_url(
        token: str,
        episode_slug: str,
        *,
        media_kind: Literal["audio", "video"],
) -> tuple[str, str]:
    """Resolve a fresh Daily Wire media URL at playback time."""
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        if not profile.use_dw_stream:
            raise HTTPException(
                status_code=404,
                detail="Daily Wire streaming is disabled for this feed",
            )
        episode, _ = get_media_for_episode(s, profile, episode_slug)
        return (
            get_dailywire_stream_url(
                profile,
                episode,
                media_kind=media_kind,
            ),
            episode.uuid,
        )


def _hls_experiment_cache_key(token: str, episode_slug: str) -> str:
    return f"{token}:{episode_slug}"


def _finish_hls_experiment(
        request: Request,
        *,
        experiment: str,
        started_at: float,
        response: Response,
        cache_hit: bool | None = None,
) -> Response:
    logger.info(
        "RSS HLS experiment=%s method=%s path=%s status=%s duration_ms=%.1f "
        "cache_hit=%s user_agent=%r accept=%r range=%r",
        experiment,
        request.method,
        request.url.path,
        response.status_code,
        (time.monotonic() - started_at) * 1000,
        cache_hit,
        request.headers.get("user-agent"),
        request.headers.get("accept"),
        request.headers.get("range"),
    )
    return response


@router.api_route("/rss/{token}/{show_slug}.xml", methods=["GET", "HEAD"])
def rss_feed(token: str, show_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        xml = render_rss_feed(s, request, profile)
    return _rss_response(xml, head_only=request.method == "HEAD")


@router.api_route("/rss/{token}/episodes/{episode_slug}", methods=["GET", "HEAD"])
def rss_feed_episode_media(token: str, episode_slug: str, request: Request):
    """Legacy extensionless media URL retained for subscribed clients."""
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


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/download.{extension}",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_download(
        token: str,
        episode_slug: str,
        extension: str,
):
    """Serve a local download through a media URL with its real extension."""
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        _, download = get_media_for_episode(s, profile, episode_slug)
        if download is None:
            raise HTTPException(status_code=404, detail="Episode uses remote media")
        file_path = Path(download.file_path)

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not available")
    if file_path.suffix.lower() != f".{extension}".lower():
        raise HTTPException(status_code=404, detail="Media extension does not match")

    return FileResponse(
        file_path,
        filename=file_path.name,
        content_disposition_type="inline",
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/audio",
    methods=["GET", "HEAD"],
)
@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/audio.m4a",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_audio(token: str, episode_slug: str, request: Request):
    url, _ = _resolve_remote_url(
        token,
        episode_slug,
        media_kind="audio",
    )
    return _temporary_stream_redirect(
        url,
        head_only=request.method == "HEAD",
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video.m3u8",
    methods=["GET", "HEAD"],
)
@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-https.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_redirect_302(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    url, _ = _resolve_remote_url(token, episode_slug, media_kind="video")
    response = _temporary_stream_redirect(
        url,
        head_only=request.method == "HEAD",
        status_code=302,
    )
    return _finish_hls_experiment(
        request,
        experiment="redirect_302",
        started_at=started_at,
        response=response,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-cached-302.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_cached_redirect_302(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    cache_key = _hls_experiment_cache_key(token, episode_slug)
    url = get_prefetched_hls_url(cache_key)
    cache_hit = url is not None
    if url is None:
        url, _ = _resolve_remote_url(token, episode_slug, media_kind="video")
        remember_prefetched_hls_url(cache_key, url)

    response = _temporary_stream_redirect(
        url,
        head_only=request.method == "HEAD",
        status_code=302,
    )
    return _finish_hls_experiment(
        request,
        experiment="cached_redirect_302",
        started_at=started_at,
        response=response,
        cache_hit=cache_hit,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-head200.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_head_200_get_302(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    if request.method == "HEAD":
        response = synthetic_hls_head_response(filename="video-head200.m3u8")
    else:
        url, _ = _resolve_remote_url(token, episode_slug, media_kind="video")
        response = _temporary_stream_redirect(url, status_code=302)

    return _finish_hls_experiment(
        request,
        experiment="head_200_get_302",
        started_at=started_at,
        response=response,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-302-headers.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_redirect_302_headers(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    url, _ = _resolve_remote_url(token, episode_slug, media_kind="video")
    response = _temporary_stream_redirect(
        url,
        head_only=request.method == "HEAD",
        status_code=302,
        extra_headers=_HLS_REDIRECT_HEADERS,
    )
    return _finish_hls_experiment(
        request,
        experiment="redirect_302_headers",
        started_at=started_at,
        response=response,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-prewarmed-raw.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_prewarmed_raw(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    response = prefetched_hls_manifest_response(
        _hls_experiment_cache_key(token, episode_slug),
        absolute_children=False,
        head_only=request.method == "HEAD",
    )
    return _finish_hls_experiment(
        request,
        experiment="prewarmed_raw",
        started_at=started_at,
        response=response,
        cache_hit=True,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-prewarmed-absolute.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_prewarmed_absolute(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    response = prefetched_hls_manifest_response(
        _hls_experiment_cache_key(token, episode_slug),
        absolute_children=True,
        head_only=request.method == "HEAD",
        forced_media_type=HLS_X_MPEGURL,
    )
    return _finish_hls_experiment(
        request,
        experiment="prewarmed_absolute",
        started_at=started_at,
        response=response,
        cache_hit=True,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-307.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_redirect_307(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    url, _ = _resolve_remote_url(token, episode_slug, media_kind="video")
    response = _temporary_stream_redirect(
        url,
        head_only=request.method == "HEAD",
        status_code=307,
    )
    return _finish_hls_experiment(
        request,
        experiment="redirect_307",
        started_at=started_at,
        response=response,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-308.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_redirect_308(
        token: str,
        episode_slug: str,
        request: Request,
):
    started_at = time.monotonic()
    url, _ = _resolve_remote_url(token, episode_slug, media_kind="video")
    response = _temporary_stream_redirect(
        url,
        head_only=request.method == "HEAD",
        status_code=308,
    )
    return _finish_hls_experiment(
        request,
        experiment="redirect_308",
        started_at=started_at,
        response=response,
    )


def _proxy_hls(
        token: str,
        episode_slug: str,
        request: Request,
        *,
        media_type: str,
) -> Response:
    url, _ = _resolve_remote_url(token, episode_slug, media_kind="video")
    return transparent_hls_proxy_response(
        url,
        head_only=request.method == "HEAD",
        forced_media_type=media_type,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-proxy.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_proxy_x(
        token: str,
        episode_slug: str,
        request: Request,
):
    return _proxy_hls(
        token,
        episode_slug,
        request,
        media_type=HLS_X_MPEGURL,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/master.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_master_proxy_x(
        token: str,
        episode_slug: str,
        request: Request,
):
    return _proxy_hls(
        token,
        episode_slug,
        request,
        media_type=HLS_X_MPEGURL,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/index.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_index_proxy_x(
        token: str,
        episode_slug: str,
        request: Request,
):
    return _proxy_hls(
        token,
        episode_slug,
        request,
        media_type=HLS_X_MPEGURL,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-proxy-apple.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_proxy_apple(
        token: str,
        episode_slug: str,
        request: Request,
):
    return _proxy_hls(
        token,
        episode_slug,
        request,
        media_type=HLS_APPLE_MPEGURL,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video-proxy-generic.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_proxy_generic(
        token: str,
        episode_slug: str,
        request: Request,
):
    return _proxy_hls(
        token,
        episode_slug,
        request,
        media_type=HLS_GENERIC_MPEGURL,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/prepared/{resource_name}",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_prepared_hls(
        token: str,
        episode_slug: str,
        resource_name: str,
        request: Request,
):
    url, episode_uuid = _resolve_remote_url(
        token,
        episode_slug,
        media_kind="video",
    )
    return prepared_hls_resource_response(
        url,
        cache_key=f"{token}:{episode_uuid}",
        resource_name=resource_name,
        head_only=request.method == "HEAD",
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video.mp4",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_mp4(token: str, episode_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        if (
            not profile.use_dw_stream
            or profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
            or profile.dw_video_method not in _CACHED_MP4_METHODS
        ):
            raise HTTPException(
                status_code=404,
                detail="Cached video is not enabled for this feed",
            )

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
