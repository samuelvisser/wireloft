from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class MediaKind(str, Enum):
    """What a probed URL turned out to point at."""

    HLS_MASTER = "hls_master"      # master playlist with one or more renditions
    HLS_MEDIA = "hls_media"        # a single media (rendition) playlist
    DIRECT_FILE = "direct_file"    # a regular downloadable file (e.g. audio .m4a)


@dataclass(frozen=True)
class VideoRendition:
    """One selectable quality variant of an HLS master playlist."""

    url: str
    width: Optional[int]
    height: Optional[int]
    bandwidth: Optional[int]
    codecs: Optional[str]

    @property
    def resolution(self) -> Optional[str]:
        if self.width is None or self.height is None:
            return None
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class MediaInfo:
    """Result of probing a media URL."""

    url: str
    kind: MediaKind
    # Present for HLS_MASTER, ordered as listed in the playlist
    renditions: tuple[VideoRendition, ...] = ()
    # Present for DIRECT_FILE when the server reports them
    content_type: Optional[str] = None
    content_length: Optional[int] = None

    @property
    def suggested_extension(self) -> str:
        """File extension (without dot) a download of this media will produce."""
        if self.kind in (MediaKind.HLS_MASTER, MediaKind.HLS_MEDIA):
            return "ts"
        return _extension_for_direct_file(self.url, self.content_type)


@dataclass
class DownloadProgress:
    """Progress snapshot passed to the progress callback."""

    bytes_downloaded: int
    total_bytes: Optional[int] = None       # known for direct files, estimated late for HLS
    segments_done: Optional[int] = None     # HLS only
    segments_total: Optional[int] = None    # HLS only

    @property
    def fraction(self) -> Optional[float]:
        """Completed fraction in [0, 1], when it can be determined."""
        if self.segments_total:
            return min(1.0, (self.segments_done or 0) / self.segments_total)
        if self.total_bytes:
            return min(1.0, self.bytes_downloaded / self.total_bytes)
        return None


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of a completed download."""

    path: str
    bytes_downloaded: int
    segments_downloaded: Optional[int] = None


# Called periodically during a download with a progress snapshot.
ProgressCallback = Callable[[DownloadProgress], None]
# Checked periodically; returning True aborts the download with DownloadCancelled.
CancelCheck = Callable[[], bool]


_CONTENT_TYPE_EXTENSIONS = {
    "audio/m4a": "m4a",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/aac": "aac",
    "video/mp4": "mp4",
    "video/mp2t": "ts",
}


def _extension_for_direct_file(url: str, content_type: Optional[str]) -> str:
    if content_type:
        normalized = content_type.split(";")[0].strip().lower()
        if normalized in _CONTENT_TYPE_EXTENSIONS:
            return _CONTENT_TYPE_EXTENSIONS[normalized]

    # Fall back to the URL path's own extension
    from urllib.parse import urlparse

    path = urlparse(url).path
    if "." in path.rsplit("/", 1)[-1]:
        ext = path.rsplit(".", 1)[-1].lower()
        if 1 <= len(ext) <= 4:
            return ext
    return "bin"
