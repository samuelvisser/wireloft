from __future__ import annotations

import os
import time
from typing import Optional

from .errors import DownloadCancelled, DownloadError
from .hls import is_master_playlist, is_playlist, parse_master_playlist, parse_media_playlist
from .http import http_get
from .models import (
    CancelCheck,
    DownloadProgress,
    DownloadResult,
    MediaInfo,
    MediaKind,
    ProgressCallback,
    VideoRendition,
)

# How often (seconds) the progress callback fires at most.
_PROGRESS_INTERVAL_S = 1.0
_CHUNK_SIZE = 256 * 1024


def probe(url: str) -> MediaInfo:
    """Inspect a media URL and report what can be downloaded from it.

    - HLS master playlist -> MediaKind.HLS_MASTER with its renditions
    - HLS media playlist  -> MediaKind.HLS_MEDIA (a single quality, no variants)
    - anything else       -> MediaKind.DIRECT_FILE with content type/length
    """
    with http_get(url) as resp:
        content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()

        looks_like_playlist = (
                "mpegurl" in content_type
                or url.split("?")[0].lower().endswith((".m3u8", ".m3u"))
        )
        if looks_like_playlist or content_type.startswith("text/"):
            text = resp.read().decode("utf-8", errors="replace")
            if is_playlist(text):
                if is_master_playlist(text):
                    return MediaInfo(
                        url=url,
                        kind=MediaKind.HLS_MASTER,
                        renditions=tuple(parse_master_playlist(text, base_url=url)),
                    )
                return MediaInfo(url=url, kind=MediaKind.HLS_MEDIA)

        content_length = resp.headers.get("Content-Length")
        return MediaInfo(
            url=url,
            kind=MediaKind.DIRECT_FILE,
            content_type=content_type or None,
            content_length=int(content_length) if content_length and content_length.isdigit() else None,
        )


def download_hls(
        rendition_url: str,
        dest_path: str,
        *,
        progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancelCheck] = None,
) -> DownloadResult:
    """Download one HLS rendition (a media playlist URL) into a single file.

    Segments are appended in order, which yields a valid MPEG-TS (or, with an
    EXT-X-MAP init segment, fragmented MP4) file without any re-encoding.
    Writes to ``<dest_path>.part`` and renames on success.
    """
    playlist_text = http_get_text_checked(rendition_url)
    playlist = parse_media_playlist(playlist_text, base_url=rendition_url)
    if not playlist.is_endlist:
        raise DownloadError("Refusing to download a live/incomplete HLS playlist (no EXT-X-ENDLIST)")

    segments_total = len(playlist.segment_urls)
    bytes_downloaded = 0
    last_report = 0.0

    part_path = dest_path + ".part"
    _ensure_parent_dir(part_path)

    def report(segments_done: int, *, force: bool = False) -> None:
        nonlocal last_report
        now = time.monotonic()
        if progress and (force or now - last_report >= _PROGRESS_INTERVAL_S):
            last_report = now
            progress(DownloadProgress(
                bytes_downloaded=bytes_downloaded,
                segments_done=segments_done,
                segments_total=segments_total,
            ))

    try:
        with open(part_path, "wb") as out:
            if playlist.init_segment_url:
                bytes_downloaded += _download_into(playlist.init_segment_url, out)

            for i, segment_url in enumerate(playlist.segment_urls):
                if should_cancel and should_cancel():
                    raise DownloadCancelled("Download cancelled")
                bytes_downloaded += _download_into(segment_url, out)
                report(i + 1)

        report(segments_total, force=True)
        os.replace(part_path, dest_path)
    except BaseException:
        _remove_quietly(part_path)
        raise

    return DownloadResult(
        path=dest_path,
        bytes_downloaded=bytes_downloaded,
        segments_downloaded=segments_total,
    )


def download_file(
        url: str,
        dest_path: str,
        *,
        progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancelCheck] = None,
) -> DownloadResult:
    """Download a direct media file (e.g. the audio .m4a) to dest_path.

    Writes to ``<dest_path>.part`` and renames on success.
    """
    part_path = dest_path + ".part"
    _ensure_parent_dir(part_path)

    bytes_downloaded = 0
    last_report = 0.0

    try:
        with http_get(url) as resp:
            content_length = resp.headers.get("Content-Length")
            total = int(content_length) if content_length and content_length.isdigit() else None

            with open(part_path, "wb") as out:
                for chunk in resp.iter_chunks(_CHUNK_SIZE):
                    if should_cancel and should_cancel():
                        raise DownloadCancelled("Download cancelled")
                    out.write(chunk)
                    bytes_downloaded += len(chunk)

                    now = time.monotonic()
                    if progress and now - last_report >= _PROGRESS_INTERVAL_S:
                        last_report = now
                        progress(DownloadProgress(bytes_downloaded=bytes_downloaded, total_bytes=total))

        if total is not None and bytes_downloaded < total:
            raise DownloadError(
                f"Incomplete download: got {bytes_downloaded} of {total} bytes from {url}"
            )
        if progress:
            progress(DownloadProgress(bytes_downloaded=bytes_downloaded, total_bytes=total))
        os.replace(part_path, dest_path)
    except BaseException:
        _remove_quietly(part_path)
        raise

    return DownloadResult(path=dest_path, bytes_downloaded=bytes_downloaded)


def http_get_text_checked(url: str) -> str:
    """Fetch a playlist URL, ensuring the response actually is a playlist."""
    with http_get(url) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    if not is_playlist(text):
        raise DownloadError(f"URL did not return an HLS playlist: {url}")
    return text


def _download_into(url: str, out) -> int:
    """Stream one URL into an open file object; returns bytes written."""
    written = 0
    with http_get(url) as resp:
        for chunk in resp.iter_chunks(_CHUNK_SIZE):
            out.write(chunk)
            written += len(chunk)
    return written


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
