from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.download_profile_types import MediaDownloadStatus


class MediaDownloadAPIBase:
    """Fields common to all media download models."""

    download_status: MediaDownloadStatus
    file_path: str


class MediaDownloadAPICreate(MediaDownloadAPIBase, RequestBase):
    """Request body for creating a media download record."""
    pass


class MediaDownloadAPIRead(MediaDownloadAPIBase, ResponseBase):
    """Response body for a media download record."""

    id: int
    created_at: datetime
    updated_at: datetime


class MediaDownloadAPIUpdate(MediaDownloadAPIBase, RequestBase):
    """Request body for updating a media download record."""
    pass
