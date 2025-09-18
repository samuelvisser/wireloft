from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.download_profile_types import MediaDownloadStatus
from typing import Union


# ---------- Strict input (create/update) ----------
class _MediaDownloadAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    download_status: MediaDownloadStatus
    file_path: str


class MediaDownloadAPICreate(_MediaDownloadAPIBaseIn):
    """Request body for creating a media download record."""
    pass


class MediaDownloadAPIUpdate(_MediaDownloadAPIBaseIn):
    """Request body for updating a media download record."""
    pass


# ---------- Lenient output (read) ----------
class _MediaDownloadAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    download_status: Union[MediaDownloadStatus, str]
    file_path: str


class MediaDownloadAPIRead(_MediaDownloadAPIBaseOut):
    """Response body for a media download record."""

    created_at: datetime
    updated_at: datetime