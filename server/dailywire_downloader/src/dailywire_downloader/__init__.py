"""Standalone media download planning, coordination, assets and publication.

The package has no dependency on WireLoft's ORM, API response models, settings,
Task Manager, or frontend. Callers prepare immutable plans and consume lifecycle
snapshots; filesystem ownership and optional download behavior live here.
"""

from .downloader import download_file, download_hls, probe
from .errors import (
    DownloadCancelled,
    DownloadError,
    EncryptedMediaError,
    FfmpegNotFoundError,
    MediaUnavailableError,
)
from .ffmpeg import convert_video_to_m4a, embed_metadata, embed_thumbnail, ffmpeg_available, remux_to_mp4
from .hls_bundle import (
    download_hls_bundle,
    hls_asset_marker,
    hls_asset_root,
    missing_hls_bundle_files,
)
from .models import (
    DownloadProgress,
    DownloadResult,
    MediaInfo,
    MediaKind,
    VideoRendition,
)

__version__ = "2.0.0"

__all__ = [
    "probe",
    "download_hls",
    "download_file",
    "download_hls_bundle",
    "hls_asset_root",
    "hls_asset_marker",
    "missing_hls_bundle_files",
    "remux_to_mp4",
    "convert_video_to_m4a",
    "embed_thumbnail",
    "embed_metadata",
    "ffmpeg_available",
    "MediaInfo",
    "MediaKind",
    "VideoRendition",
    "DownloadProgress",
    "DownloadResult",
    "DownloadError",
    "MediaUnavailableError",
    "EncryptedMediaError",
    "DownloadCancelled",
    "FfmpegNotFoundError",
    "__version__",
]

from .plan import DownloadPlan, ResolvedDownloadSource, SidecarSpec, build_download_plan
from .lifecycle import DownloadTracker, DownloadSnapshot
from .coordinator import DownloadExecution, execute_download_plan

__all__ += ["DownloadPlan", "ResolvedDownloadSource", "SidecarSpec", "build_download_plan",
            "DownloadTracker", "DownloadSnapshot", "DownloadExecution", "execute_download_plan"]
