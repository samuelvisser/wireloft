"""Standalone HLS / direct-file media downloader used by Wireloft.

This package knows nothing about Daily Wire's API or Wireloft's database. It
answers two questions for a media URL: "what can be downloaded from this?"
(:func:`probe`) and "download exactly this" (:func:`download_hls` /
:func:`download_file`). Choosing *which* rendition to download is the caller's
job.
"""

from .downloader import download_file, download_hls, probe
from .errors import (
    DownloadCancelled,
    DownloadError,
    EncryptedMediaError,
    MediaUnavailableError,
)
from .models import (
    DownloadProgress,
    DownloadResult,
    MediaInfo,
    MediaKind,
    VideoRendition,
)

__version__ = "1.0.0"

__all__ = [
    "probe",
    "download_hls",
    "download_file",
    "MediaInfo",
    "MediaKind",
    "VideoRendition",
    "DownloadProgress",
    "DownloadResult",
    "DownloadError",
    "MediaUnavailableError",
    "EncryptedMediaError",
    "DownloadCancelled",
    "__version__",
]
