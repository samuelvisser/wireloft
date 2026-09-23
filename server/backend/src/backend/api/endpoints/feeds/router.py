from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse

from .cached_video import get_cached_mp4_path, prepare_cached_mp4
from .service import (
    can_use_dailywire_for_episode,
    get_dailywire_stream_url,
    get_episode_for_feed,
    get_local_download_for_episode,
    get_rss_stream_profile_by_token,
    remember_live_episode_handoff,
    render_rss_feed,
)
from backend.app import db_session
from backend.types.episode_types import EpisodePublishStatus
from backend.types.local_media_profile_types import PreferredFormat
from backend.types.stream_profile_types import (
    RSS_AUDIO_PRIMARY_OUTPUT_MODES,
    RSS_HLS_OUTPUT_MODES,
    RSS_MP4_OUTPUT_MODES,
)
from dailywire_downloader import hls_asset_root
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


router = APIRouter(prefix="/feeds", tags=["Feeds"])

_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
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
        **_NO_CACHE_HEADERS,
    }
    if file_path is not None:
        headers["Content-Length"] = str(file_path.stat().st_size)

    response = Response(content=b"", media_type="video/mp4", headers=headers)
    if file_path is None:
        response.headers.pop("content-length", None)
    return response


def _commit_feed_state_if_changed(s) -> None:
    if s.dirty:
        s.commit()


def _resolved_download_path(s, download) -> Path | None:
    if download is None:
        return None
    return resolve_media_download_file(
        s,
        download,
        release_read_transaction=True,
    )


@router.api_route("/rss/{token}/{show_slug}.xml", methods=["GET", "HEAD"])
def rss_feed(token: str, show_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        xml = render_rss_feed(s, request, profile)
        _commit_feed_state_if_changed(s)
    return _rss_response(xml, head_only=request.method == "HEAD")


@router.api_route("/rss/{token}/episodes/{episode_slug}", methods=["GET", "HEAD"])
def rss_feed_episode_media(token: str, episode_slug: str, request: Request):
    """Keep previously published generic media URLs usable after the stable split."""
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        get_episode_for_feed(s, profile, episode_slug)
        _commit_feed_state_if_changed(s)
        audio_primary = (
            profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
            or profile.video_output_mode in RSS_AUDIO_PRIMARY_OUTPUT_MODES
        )

    suffix = "audio.m4a" if audio_primary else "video.mp4"
    target = f"{str(request.url).rstrip('/')}/{suffix}"
    headers = {"Location": target, **_NO_CACHE_HEADERS}
    if request.method == "HEAD":
        return Response(status_code=307, headers=headers)
    return RedirectResponse(target, status_code=307, headers=_NO_CACHE_HEADERS)


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/audio.m4a",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_audio(token: str, episode_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        episode = get_episode_for_feed(s, profile, episode_slug)
        _commit_feed_state_if_changed(s)

        download = get_local_download_for_episode(
            s,
            profile,
            episode,
            kind="audio",
        )
        file_path = _resolved_download_path(s, download)
        if file_path is not None:
            return FileResponse(
                file_path,
                filename=file_path.name,
                content_disposition_type="inline",
                media_type="audio/mp4",
                headers=_NO_CACHE_HEADERS,
            )

        if not can_use_dailywire_for_episode(profile, episode):
            raise HTTPException(
                status_code=404,
                detail="No local audio is available and Daily Wire streaming is disabled",
            )

        return _temporary_stream_redirect(
            get_dailywire_stream_url(
                profile,
                episode,
                media_kind="audio",
            ),
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
            profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
            or profile.video_output_mode not in RSS_MP4_OUTPUT_MODES
        ):
            raise HTTPException(status_code=404, detail="MP4 video is not enabled for this feed")

        episode = get_episode_for_feed(s, profile, episode_slug)
        _commit_feed_state_if_changed(s)
        if episode.publish_status == EpisodePublishStatus.LIVE.value:
            raise HTTPException(
                status_code=404,
                detail="Live video is available through the HLS enclosure only",
            )
        download = get_local_download_for_episode(
            s,
            profile,
            episode,
            kind="mp4",
        )
        file_path = _resolved_download_path(s, download)
        if file_path is not None and file_path.suffix.lower() == ".mp4":
            return FileResponse(
                file_path,
                filename=file_path.name,
                content_disposition_type="inline",
                media_type="video/mp4",
                headers=_NO_CACHE_HEADERS,
            )

        if not can_use_dailywire_for_episode(profile, episode):
            raise HTTPException(
                status_code=404,
                detail="No local MP4 is available and Daily Wire streaming is disabled",
            )

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
        headers=_NO_CACHE_HEADERS,
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/video.m3u8",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_video_hls(token: str, episode_slug: str, request: Request):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        if (
            profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
            or profile.video_output_mode not in RSS_HLS_OUTPUT_MODES
        ):
            raise HTTPException(status_code=404, detail="HLS video is not enabled for this feed")

        episode = get_episode_for_feed(s, profile, episode_slug)
        _commit_feed_state_if_changed(s)
        download = get_local_download_for_episode(
            s,
            profile,
            episode,
            kind="hls",
        )
        file_path = _resolved_download_path(s, download)
        if file_path is not None and file_path.suffix.lower() == ".m3u8":
            return FileResponse(
                file_path,
                filename="video.m3u8",
                content_disposition_type="inline",
                media_type="application/x-mpegURL",
                headers=_NO_CACHE_HEADERS,
            )

        if not can_use_dailywire_for_episode(profile, episode):
            raise HTTPException(
                status_code=404,
                detail="No local HLS video is available and Daily Wire streaming is disabled",
            )

        source_url = get_dailywire_stream_url(
            profile,
            episode,
            media_kind="video",
        )
        if request.method != "HEAD":
            remember_live_episode_handoff(profile, episode)
            _commit_feed_state_if_changed(s)

    return _temporary_stream_redirect(
        source_url,
        head_only=request.method == "HEAD",
    )


@router.api_route(
    "/rss/{token}/episodes/{episode_slug}/hls/{asset_path:path}",
    methods=["GET", "HEAD"],
)
def rss_feed_episode_hls_asset(
    token: str,
    episode_slug: str,
    asset_path: str,
):
    with db_session() as s:
        profile = get_rss_stream_profile_by_token(s, token)
        if profile.video_output_mode not in RSS_HLS_OUTPUT_MODES:
            raise HTTPException(status_code=404, detail="HLS video is not enabled for this feed")

        episode = get_episode_for_feed(s, profile, episode_slug)
        _commit_feed_state_if_changed(s)
        download = get_local_download_for_episode(
            s,
            profile,
            episode,
            kind="hls",
        )
        master_path = _resolved_download_path(s, download)
        if master_path is None:
            raise HTTPException(status_code=404, detail="Local HLS video is not available")

        root = hls_asset_root(master_path).resolve()
        candidate = (root / asset_path).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="HLS asset not found")

    media_type = mimetypes.guess_type(candidate.name)[0]
    if candidate.suffix.lower() == ".m3u8":
        media_type = "application/x-mpegURL"
    elif candidate.suffix.lower() == ".ts":
        media_type = "video/mp2t"

    return FileResponse(
        candidate,
        filename=candidate.name,
        content_disposition_type="inline",
        media_type=media_type,
    )
