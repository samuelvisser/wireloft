from __future__ import annotations

from backend.types.local_media_profile_types import (
    LocalMediaProfileStorageMode,
    LocalMediaProfileThumbnailMode,
)
from config import get_settings
from config.settings.submodels import DownloadMode, ThumbnailMode


def effective_download_mode(local_media_profile) -> DownloadMode:
    """Resolve a Local Media Profile override against the current system default."""
    system_mode = DownloadMode(get_settings().download_settings.download_mode)
    profile_mode = LocalMediaProfileStorageMode(
        getattr(
            local_media_profile,
            "download_mode",
            LocalMediaProfileStorageMode.SYSTEM.value,
        )
    )
    if profile_mode is LocalMediaProfileStorageMode.SYSTEM:
        return system_mode
    return DownloadMode(profile_mode.value)


def effective_thumbnail_mode(local_media_profile) -> ThumbnailMode:
    """Resolve a Local Media Profile thumbnail override against the system default."""
    system_mode = ThumbnailMode(get_settings().download_settings.thumbnail_mode)
    profile_mode = LocalMediaProfileThumbnailMode(
        getattr(
            local_media_profile,
            "thumbnail_mode",
            LocalMediaProfileThumbnailMode.SYSTEM.value,
        )
    )
    if profile_mode is LocalMediaProfileThumbnailMode.SYSTEM:
        return system_mode
    return ThumbnailMode(profile_mode.value)
