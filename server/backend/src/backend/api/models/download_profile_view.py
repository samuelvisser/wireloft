from __future__ import annotations

from typing import Union

from backend.api.models.download_profile import DownloadProfileAPIRead

from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPIRead
from backend.api.models.series_download_profile import SeriesDownloadProfileAPIRead


# ---------- Lenient output (read) ----------
class DownloadProfileAPIReadView(DownloadProfileAPIRead):
    """Denormalized view for a download profile adding related display fields."""

    show_title: str
    show_slug: str
    local_media_profile_preferred_format: str
    download_profile_impl: Union[PodcastDownloadProfileAPIRead, SeriesDownloadProfileAPIRead]
