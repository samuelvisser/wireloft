from __future__ import annotations

from datetime import datetime
from typing import Union

from backend.api.models.base import ResponseBase
from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPIRead
from backend.api.models.series_download_profile import SeriesDownloadProfileAPIRead
from backend.types.download_profile_types import DownloadProfileType


class DownloadProfileAPIRead(ResponseBase):
    """Unified response body for a download profile (any type).

    Represents the base download profile record with its discriminator `type`.
    Create/Update/Delete of concrete profiles should be done via the
    podcast/series specific endpoints.
    """

    id: int
    show_id: int
    local_media_profile_id: int
    enable_profile: bool
    type: DownloadProfileType

    created_at: datetime
    updated_at: datetime


class DownloadProfileAPIReadView(DownloadProfileAPIRead):
    """Denormalized view for a download profile adding related display fields.

    Extends DownloadProfileAPIRead with:
    - show_title: the title of the related show
    - local_media_profile_preferred_format: preferred format configured on the local media profile
    - download_profile_impl: the concrete profile payload (podcast or series)
    """

    show_title: str
    show_slug: str
    local_media_profile_preferred_format: str
    download_profile_impl: Union[PodcastDownloadProfileAPIRead, SeriesDownloadProfileAPIRead]
