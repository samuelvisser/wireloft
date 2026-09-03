from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from fastapi import HTTPException, Response

from .hls_experiments import HLS_X_MPEGURL
from config import get_settings


_MAX_PLAYLIST_BYTES = 2 * 1024 * 1024
_PREFETCH_CACHE_DIRECTORY = ".wireloft-rss-hls-prefetch"
_PREFETCH_MAX_AGE_SECONDS = 15 * 60
_HLS_URI_ATTRIBUTE_RE = re.compile(
    r'(?P<prefix>\bURI=)(?P<quote>["\'])(?P<uri>[^"\']+)(?P=quote)'
)
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
_COPY_RESPONSE_HEADERS = (
    "Content-Type",
    "Content-Range",
    "Accept-Ranges",
    "ETag",
    "Last-Modified",
    "Cache-Control",
    "Expires",
)


def _prefetch_root() -> Path:
    return (
        Path(get_settings().download_settings.download_root)
        / _PREFETCH_CACHE_DIRECTORY
    )


def _prefetch_directory(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return _prefetch_root() / digest


def _is_current(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return (
        stat.st_size > 0
        and time.time() - stat.st_mtime < _PREFETCH_MAX_AGE_SECONDS
    )


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def remember_prefetched_hls_url(cache_key: str, url: str) -> None:
    """Remember a recently resolved signed HLS URL for the instant-302 probe."""
    _atomic_write_text(_prefetch_directory(cache_key) / "source.url", url)


def get_prefetched_hls_url(cache_key: str) -> str | None:
    path = _prefetch_directory(cache_key) / "source.url"
    if not _is_current(path):
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _resolve_hls_uri(base_url: str, uri: str) -> str:
    """Resolve a child URI and inherit signed query data when it is omitted."""
    resolved = urljoin(base_url, uri)
    base = urlsplit(base_url)
    child = urlsplit(resolved)
    if (
        not child.query
        and base.query
        and child.scheme == base.scheme
        and child.hostname == base.hostname
    ):
        child = child._replace(query=base.query)
    return urlunsplit(child)


def _rewrite_hls_playlist_absolute(playlist: str, *, base_url: str) -> str:
    had_trailing_newline = playlist.endswith("\n")
    rewritten: list[str] = []

    for line in playlist.splitlines():
        stripped = line.strip()
        if not stripped:
            rewritten.append(line)
            continue

        if stripped.startswith("#"):
            def replace_uri(match: re.Match[str]) -> str:
                absolute = _resolve_hls_uri(base_url, match.group("uri"))
                return (
                    f'{match.group("prefix")}{match.group("quote")}'
                    f'{absolute}{match.group("quote")}'
                )

            rewritten.append(_HLS_URI_ATTRIBUTE_RE.sub(replace_uri, line))
        else:
            rewritten.append(_resolve_hls_uri(base_url, stripped))

    result = "\n".join(rewritten)
    return result + "\n" if had_trailing_newline else result


def _fetch_hls_manifest(url: str) -> tuple[bytes, str, dict[str, str]]:
    request = UrlRequest(
        url,
        headers={
            "Accept": (
                "application/vnd.apple.mpegurl, application/x-mpegURL, "
                "application/mpegurl, */*"
            ),
            "Accept-Encoding": "identity",
            "User-Agent": "WireLoft/1.1-rss-prefetch-experiment",
        },
    )
    try:
        with urlopen(request, timeout=20) as upstream:
            payload = upstream.read(_MAX_PLAYLIST_BYTES + 1)
            final_url = upstream.geturl()
            response_headers = {
                name: value
                for name in _COPY_RESPONSE_HEADERS
                if (value := upstream.headers.get(name))
            }
    except (HTTPError, URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Daily Wire HLS playlist is currently unavailable",
        ) from exc

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
    return payload, final_url, response_headers


def prewarm_hls_manifests(cache_key: str, url: str) -> None:
    """Cache both untouched and absolute-child variants before the client probes."""
    payload, final_url, response_headers = _fetch_hls_manifest(url)
    try:
        playlist = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="Daily Wire returned an invalid HLS playlist",
        ) from exc

    directory = _prefetch_directory(cache_key)
    _atomic_write_bytes(directory / "raw.m3u8", payload)
    _atomic_write_text(
        directory / "absolute.m3u8",
        _rewrite_hls_playlist_absolute(playlist, base_url=final_url),
    )
    _atomic_write_text(
        directory / "headers.json",
        json.dumps(response_headers, separators=(",", ":")),
    )
    remember_prefetched_hls_url(cache_key, url)


def prefetched_hls_manifest_response(
        cache_key: str,
        *,
        absolute_children: bool,
        head_only: bool,
        forced_media_type: str | None = None,
) -> Response:
    directory = _prefetch_directory(cache_key)
    path = directory / ("absolute.m3u8" if absolute_children else "raw.m3u8")
    if not _is_current(path):
        raise HTTPException(
            status_code=503,
            detail="The pre-warmed HLS experiment cache is empty or expired",
        )

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="The pre-warmed HLS experiment cache is unavailable",
        ) from exc

    response_headers: dict[str, str] = {}
    headers_path = directory / "headers.json"
    if _is_current(headers_path):
        try:
            stored = json.loads(headers_path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                response_headers.update(
                    (str(key), str(value))
                    for key, value in stored.items()
                )
        except (OSError, ValueError, TypeError):
            pass

    response_headers.update(_NO_CACHE_HEADERS)
    response_headers["Content-Disposition"] = 'inline; filename="video.m3u8"'
    response_headers["Content-Length"] = str(len(payload))
    if forced_media_type:
        response_headers["Content-Type"] = forced_media_type
    elif "Content-Type" not in response_headers:
        response_headers["Content-Type"] = HLS_X_MPEGURL

    return Response(
        content=b"" if head_only else payload,
        status_code=200,
        headers=response_headers,
    )


def synthetic_hls_head_response(
        *,
        media_type: str = HLS_X_MPEGURL,
        filename: str = "video.m3u8",
) -> Response:
    """Return an immediate HLS-looking HEAD response without resolving Daily Wire."""
    response = Response(
        content=b"",
        status_code=200,
        headers={
            **_NO_CACHE_HEADERS,
            "Content-Type": media_type,
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
    if "content-length" in response.headers:
        del response.headers["content-length"]
    return response
