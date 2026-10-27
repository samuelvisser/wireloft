"""Acquire segmented HLS WebVTT and convert it to Plex-friendly UTF-8 SRT.

HLS subtitle segments are independent WebVTT documents, not text that can be
concatenated. In particular, X-TIMESTAMP-MAP maps local cue timestamps into
the MPEG-TS timebase and may change between segments.
"""
from __future__ import annotations

import html
import re
from collections.abc import Callable
from urllib.parse import urlsplit

from .errors import DownloadCancelled, DownloadError
from .hls import is_playlist, parse_media_playlist
from .http import http_get
from .models import DownloadProgress

_CUE_TIME = r"(?:\d{2,}:)?\d{2}:\d{2}[.,]\d{3}"
_TIMING = re.compile(rf"^\s*({_CUE_TIME})\s+-->\s+({_CUE_TIME})(?:\s+.*)?$")
_TIMESTAMP_MAP = re.compile(r"^X-TIMESTAMP-MAP=(.*)$", re.MULTILINE)
_INLINE_TAG = re.compile(r"<[^>]*>")
_CLOCK_WRAP_SECONDS = (1 << 33) / 90000
_MAX_SEGMENTS = 10000


def _timestamp(value: str) -> int:
    """Parse hours:minutes:seconds or minutes:seconds into milliseconds."""
    parts = value.replace(",", ".").split(":")
    seconds, fraction = parts[-1].split(".", 1)
    if len(parts) == 3:
        hours, minutes = int(parts[0]), int(parts[1])
    else:
        hours, minutes = 0, int(parts[0])
    return (((hours * 60 + minutes) * 60 + int(seconds)) * 1000) + int(fraction)


def _format_timestamp(milliseconds: int) -> str:
    milliseconds = max(0, milliseconds)
    hours, rest = divmod(milliseconds, 3600000)
    minutes, rest = divmod(rest, 60000)
    seconds, fraction = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{fraction:03}"


def _map_offset_ms(document: str) -> int | None:
    """Return the MPEGTS-to-LOCAL offset; a 33-bit PTS can wrap."""
    match = _TIMESTAMP_MAP.search(document)
    if not match:
        return None
    attrs = dict(
        item.strip().split(":", 1)
        for item in match.group(1).split(",")
        if ":" in item
    )
    if "LOCAL" not in attrs or "MPEGTS" not in attrs:
        return None
    try:
        return round(int(attrs["MPEGTS"]) / 90) - _timestamp(attrs["LOCAL"])
    except ValueError:
        return None


def _cues(document: str) -> list[tuple[int, int, str]]:
    text = document.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("WEBVTT"):
        raise DownloadError("HLS subtitle segment is not WebVTT")
    result: list[tuple[int, int, str]] = []
    for block in re.split(r"\n\s*\n", text)[1:]:
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        timing = next((_TIMING.match(line) for line in lines[:2] if _TIMING.match(line)), None)
        if timing is None:
            continue
        timing_index = next(index for index, line in enumerate(lines[:2]) if _TIMING.match(line))
        body = "\n".join(html.unescape(_INLINE_TAG.sub("", line)).strip() for line in lines[timing_index + 1:]).strip()
        if not body:
            continue
        start, end = _timestamp(timing.group(1)), _timestamp(timing.group(2))
        if end > start:
            result.append((start, end, body))
    return result


def _fetch_limited(
    url: str, remaining_bytes: int, should_cancel: Callable[[], bool],
) -> bytes:
    if remaining_bytes <= 0:
        raise DownloadError("HLS subtitles exceed the configured size limit")
    chunks: list[bytes] = []
    size = 0
    if should_cancel():
        raise DownloadCancelled("Subtitle download canceled")
    with http_get(url) as response:
        for chunk in response.iter_chunks(256 * 1024):
            if should_cancel():
                raise DownloadCancelled("Subtitle download canceled")
            size += len(chunk)
            if size > remaining_bytes:
                raise DownloadError("HLS subtitles exceed the configured size limit")
            chunks.append(chunk)
    return b"".join(chunks)


def download_hls_webvtt(
    playlist_url: str, *, maximum_bytes: int,
    should_cancel: Callable[[], bool],
    progress: Callable[[DownloadProgress], None] | None = None,
) -> bytes:
    """Download VOD subtitles and return one language track as UTF-8 SRT."""
    raw_playlist = _fetch_limited(playlist_url, maximum_bytes, should_cancel)
    text = raw_playlist.decode("utf-8-sig")
    if not is_playlist(text):
        raise DownloadError("HLS subtitle URL did not return a playlist")
    if "#EXT-X-BYTERANGE:" in text or "#EXT-X-MAP:" in text:
        raise DownloadError("Byte-range or fMP4 HLS subtitles require a different subtitle format")
    media = parse_media_playlist(text, playlist_url)
    if not media.is_endlist:
        raise DownloadError("Live HLS subtitles cannot yet be saved as a complete sidecar")
    if len(media.segment_urls) > _MAX_SEGMENTS:
        raise DownloadError("HLS subtitle playlist contains too many segments")

    # EXTINF durations provide a fallback for WebVTT without timestamp maps.
    durations = []
    for line in text.splitlines():
        if line.startswith("#EXTINF:"):
            try:
                durations.append(float(line.split(":", 1)[1].split(",", 1)[0]))
            except ValueError as exc:
                raise DownloadError("Invalid HLS subtitle segment duration") from exc
    if len(durations) != len(media.segment_urls):
        raise DownloadError("HLS subtitle playlist has inconsistent segment durations")

    consumed = len(raw_playlist)
    offset_origin: int | None = None
    position_ms = 0
    seen: set[tuple[int, int, str]] = set()
    entries: list[tuple[int, int, str]] = []
    for index, (url, duration) in enumerate(zip(media.segment_urls, durations)):
        if urlsplit(url).scheme not in {"https", "http"}:
            raise DownloadError("HLS subtitle segment requires an HTTP(S) URL")
        data = _fetch_limited(url, maximum_bytes - consumed, should_cancel)
        consumed += len(data)
        document = data.decode("utf-8-sig")
        mapping = _map_offset_ms(document)
        if mapping is not None:
            if offset_origin is None:
                offset_origin = mapping
            # Correct for the 33-bit MPEGTS counter rolling over mid-stream.
            relative = (mapping - offset_origin) / 1000
            if relative > _CLOCK_WRAP_SECONDS / 2:
                relative -= _CLOCK_WRAP_SECONDS
            elif relative < -_CLOCK_WRAP_SECONDS / 2:
                relative += _CLOCK_WRAP_SECONDS
            correction = round(relative * 1000)
        else:
            correction = 0
        for start, end, body in _cues(document):
            # WebVTT without a map may use either global or segment-relative
            # timestamps. Apply EXTINF only when cues clearly reset to zero.
            shift = correction if mapping is not None else (
                position_ms if index > 0 and start < position_ms - 1000 else 0
            )
            item = (max(0, start + shift), max(0, end + shift), body)
            if item[1] > item[0] and item not in seen:
                seen.add(item)
                entries.append(item)
        position_ms += round(duration * 1000)
        if progress is not None:
            progress(DownloadProgress(consumed, maximum_bytes, segments_done=index + 1, segments_total=len(media.segment_urls)))

    entries.sort(key=lambda item: (item[0], item[1]))
    if not entries:
        raise DownloadError("HLS subtitle playlist contains no usable cues")
    content = "".join(
        f"{index}\n{_format_timestamp(start)} --> {_format_timestamp(end)}\n{body}\n\n"
        for index, (start, end, body) in enumerate(entries, 1)
    ).encode("utf-8")
    if len(content) > maximum_bytes:
        raise DownloadError("Converted HLS subtitles exceed the configured size limit")
    return content
