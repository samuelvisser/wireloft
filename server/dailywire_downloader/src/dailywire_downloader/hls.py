from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from .errors import DownloadError, EncryptedMediaError
from .models import VideoRendition

_ATTR_RE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def parse_attribute_list(attr_string: str) -> dict[str, str]:
    """Parse an HLS attribute list ('KEY=VALUE,KEY="VAL,UE"') into a dict."""
    attrs: dict[str, str] = {}
    for key, value in _ATTR_RE.findall(attr_string):
        attrs[key] = value.strip('"')
    return attrs


def is_playlist(text: str) -> bool:
    return text.lstrip().startswith("#EXTM3U")


def is_master_playlist(text: str) -> bool:
    return "#EXT-X-STREAM-INF" in text


def parse_master_playlist(text: str, base_url: str) -> list[VideoRendition]:
    """Extract the video renditions from a master playlist."""
    renditions: list[VideoRendition] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue

        attrs = parse_attribute_list(line[len("#EXT-X-STREAM-INF:"):])

        # The URI is the next non-comment, non-empty line
        uri = next((l.strip() for l in lines[i + 1:] if l.strip() and not l.startswith("#")), None)
        if uri is None:
            continue

        width: Optional[int] = None
        height: Optional[int] = None
        resolution = attrs.get("RESOLUTION")
        if resolution and "x" in resolution:
            try:
                w, h = resolution.lower().split("x", 1)
                width, height = int(w), int(h)
            except ValueError:
                pass

        bandwidth: Optional[int] = None
        for key in ("AVERAGE-BANDWIDTH", "BANDWIDTH"):
            if attrs.get(key, "").isdigit():
                bandwidth = int(attrs[key])
                break

        renditions.append(VideoRendition(
            url=urljoin(base_url, uri),
            width=width,
            height=height,
            bandwidth=bandwidth,
            codecs=attrs.get("CODECS"),
        ))

    return renditions


@dataclass(frozen=True)
class MediaPlaylist:
    """The downloadable contents of a media (rendition) playlist."""

    segment_urls: tuple[str, ...]
    # fMP4 initialization segment (EXT-X-MAP), None for MPEG-TS streams
    init_segment_url: Optional[str]
    is_endlist: bool


def parse_media_playlist(text: str, base_url: str) -> MediaPlaylist:
    """Extract segment URLs from a media playlist.

    Raises EncryptedMediaError when the playlist declares any non-NONE
    encryption; this downloader intentionally does not implement DRM.
    """
    segment_urls: list[str] = []
    init_segment_url: Optional[str] = None
    is_endlist = False
    expect_segment = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("#EXT-X-KEY:") or line.startswith("#EXT-X-SESSION-KEY:"):
            attrs = parse_attribute_list(line.split(":", 1)[1])
            if attrs.get("METHOD", "NONE").upper() != "NONE":
                raise EncryptedMediaError(
                    f"Encrypted HLS stream (METHOD={attrs.get('METHOD')}) is not supported"
                )
            continue

        if line.startswith("#EXT-X-MAP:"):
            attrs = parse_attribute_list(line.split(":", 1)[1])
            if "URI" in attrs:
                init_segment_url = urljoin(base_url, attrs["URI"])
            continue

        if line.startswith("#EXTINF:"):
            expect_segment = True
            continue

        if line.startswith("#EXT-X-ENDLIST"):
            is_endlist = True
            continue

        if line.startswith("#"):
            continue

        if expect_segment:
            segment_urls.append(urljoin(base_url, line))
            expect_segment = False

    if not segment_urls:
        raise DownloadError("Media playlist contains no segments")

    return MediaPlaylist(
        segment_urls=tuple(segment_urls),
        init_segment_url=init_segment_url,
        is_endlist=is_endlist,
    )
