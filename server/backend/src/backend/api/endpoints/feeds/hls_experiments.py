from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse

from config import get_settings


logger = logging.getLogger(__name__)

HLS_X_MPEGURL = "application/x-mpegURL"
HLS_APPLE_MPEGURL = "application/vnd.apple.mpegurl"
HLS_GENERIC_MPEGURL = "application/mpegurl"

_MAX_PLAYLIST_BYTES = 2 * 1024 * 1024
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
_COPY_RESPONSE_HEADERS = (
    "Content-Type",
    "Content-Length",
    "Content-Range",
    "Accept-Ranges",
    "ETag",
    "Last-Modified",
    "Cache-Control",
    "Expires",
)

_PREPARED_CACHE_DIRECTORY = ".wireloft-rss-hls-experiment"
_PREPARED_MAX_AGE_SECONDS = 24 * 60 * 60
_PREPARED_LOCKS: dict[Path, threading.Lock] = {}
_PREPARED_LOCKS_GUARD = threading.Lock()


def transparent_hls_proxy_response(
        url: str,
        *,
        head_only: bool,
        forced_media_type: str | None = None,
) -> Response:
    """Return the upstream HLS manifest bytes without rewriting the playlist."""
    headers = {
        "Accept": (
            "application/vnd.apple.mpegurl, application/x-mpegURL, "
            "application/mpegurl, */*"
        ),
        "Accept-Encoding": "identity",
        "User-Agent": "WireLoft/1.1-rss-experiment",
    }

    method = "HEAD" if head_only else "GET"
    try:
        upstream = urlopen(
            UrlRequest(url, headers=headers, method=method),
            timeout=20,
        )
    except HTTPError as exc:
        if not head_only or exc.code not in {405, 501}:
            raise HTTPException(
                status_code=502,
                detail="Daily Wire HLS playlist is currently unavailable",
            ) from exc
        try:
            upstream = urlopen(
                UrlRequest(url, headers=headers, method="GET"),
                timeout=20,
            )
        except (HTTPError, URLError, TimeoutError) as fallback_exc:
            raise HTTPException(
                status_code=502,
                detail="Daily Wire HLS playlist is currently unavailable",
            ) from fallback_exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Daily Wire HLS playlist is currently unavailable",
        ) from exc

    try:
        status_code = getattr(upstream, "status", 200)
        response_headers: dict[str, str] = {}
        for name in _COPY_RESPONSE_HEADERS:
            value = upstream.headers.get(name)
            if value:
                response_headers[name] = value
        if forced_media_type:
            response_headers["Content-Type"] = forced_media_type

        if head_only:
            return Response(
                content=b"",
                status_code=status_code,
                headers=response_headers,
            )

        payload = upstream.read(_MAX_PLAYLIST_BYTES + 1)
        if len(payload) > _MAX_PLAYLIST_BYTES:
            raise HTTPException(
                status_code=502,
                detail="Daily Wire HLS playlist is unexpectedly large",
            )
        if not payload.lstrip().startswith(b"#EXTM3U"):
            raise HTTPException(
                status_code=502,
                detail="Daily Wire returned an invalid HLS playlist",
            )

        # Response would otherwise calculate Content-Length from the body.
        # Preserve the upstream value only when it actually matches the bytes
        # that are being returned.
        response_headers["Content-Length"] = str(len(payload))
        return Response(
            content=payload,
            status_code=status_code,
            headers=response_headers,
        )
    finally:
        upstream.close()


def _prepared_root() -> Path:
    return (
        Path(get_settings().download_settings.download_root)
        / _PREPARED_CACHE_DIRECTORY
    )


def _prepared_path(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return _prepared_root() / digest


def _lock_for(path: Path) -> threading.Lock:
    with _PREPARED_LOCKS_GUARD:
        return _PREPARED_LOCKS.setdefault(path, threading.Lock())


def _is_current(index: Path) -> bool:
    try:
        stat = index.stat()
    except OSError:
        return False
    return (
        stat.st_size > 0
        and time.time() - stat.st_mtime < _PREPARED_MAX_AGE_SECONDS
    )


def _cleanup_expired_prepared_hls(root: Path) -> None:
    cutoff = time.time() - _PREPARED_MAX_AGE_SECONDS
    try:
        directories = list(root.iterdir())
    except OSError:
        return

    for directory in directories:
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        index = directory / "video.m3u8"
        try:
            modified = (
                index.stat().st_mtime
                if index.is_file()
                else directory.stat().st_mtime
            )
            if modified < cutoff:
                shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            continue


def materialize_prepared_hls(source_url: str, *, cache_key: str) -> Path:
    """Prepare a conventional MPEG-TS VOD HLS package for compatibility tests."""
    target = _prepared_path(cache_key)
    index = target / "video.m3u8"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="RSS HLS experiment cache is not writable",
        ) from exc

    if _is_current(index):
        return index

    with _lock_for(target):
        if _is_current(index):
            return index

        _cleanup_expired_prepared_hls(target.parent)
        temporary = target.parent / f".{target.name}.{uuid4().hex}.part"
        temporary.mkdir(parents=True, exist_ok=False)
        ffmpeg_path = get_settings().download_settings.ffmpeg_path
        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-nostats",
            "-nostdin",
            "-y",
            "-fflags", "+genpts",
            "-i", source_url,
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-c", "copy",
            "-hls_time", "6",
            "-hls_list_size", "0",
            "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments",
            "-hls_segment_filename", str(temporary / "segment%05d.ts"),
            "-f", "hls",
            str(temporary / "video.m3u8"),
        ]
        try:
            try:
                completed = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="ffmpeg is required for the prepared HLS experiment",
                ) from exc
            except OSError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Could not prepare the HLS experiment",
                ) from exc

            prepared_index = temporary / "video.m3u8"
            if completed.returncode != 0 or not _is_current(prepared_index):
                logger.error(
                    "ffmpeg failed to prepare RSS HLS experiment (exit %s): %s",
                    completed.returncode,
                    (completed.stderr or "")[-4000:],
                )
                raise HTTPException(
                    status_code=502,
                    detail="Daily Wire video could not be prepared as HLS",
                )

            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            os.replace(temporary, target)
            return index
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)


def prepared_hls_resource_response(
        source_url: str,
        *,
        cache_key: str,
        resource_name: str,
        head_only: bool,
) -> Response:
    if (
        Path(resource_name).name != resource_name
        or resource_name in {"", ".", ".."}
    ):
        raise HTTPException(status_code=400, detail="Invalid HLS resource")

    index = materialize_prepared_hls(source_url, cache_key=cache_key)
    resource = index.parent / resource_name
    if not resource.is_file():
        raise HTTPException(status_code=404, detail="Prepared HLS resource not found")

    suffix = resource.suffix.lower()
    media_type = (
        HLS_APPLE_MPEGURL
        if suffix in {".m3u8", ".m3u"}
        else "video/mp2t"
        if suffix == ".ts"
        else "application/octet-stream"
    )

    if head_only:
        return Response(
            content=b"",
            media_type=media_type,
            headers={
                **_NO_CACHE_HEADERS,
                "Accept-Ranges": "bytes",
                "Content-Length": str(resource.stat().st_size),
            },
        )

    return FileResponse(
        resource,
        media_type=media_type,
        headers=_NO_CACHE_HEADERS,
    )
