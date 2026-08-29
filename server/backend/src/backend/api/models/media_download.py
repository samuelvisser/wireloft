from datetime import datetime
from typing import Optional, Union

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.download_profile_types import MediaDownloadStatus


# ---------- Strict input (create/update) ----------
class EpisodeDownloadAPICreate(RequestBase):
    """Request body for starting an episode download for a Local Media Profile."""

    local_media_profile_id: int


class MovieDownloadAPICreate(RequestBase):
    """Request body for starting a movie download for a Local Media Profile."""

    local_media_profile_id: int


class MediaDownloadAPIUpdate(RequestBase):
    """Request body for updating a media download record."""

    download_status: MediaDownloadStatus
    file_path: str


# ---------- Lenient output (read) ----------
class _MediaDownloadAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    type: str
    media_item_id: int
    local_media_profile_id: int
    download_status: Union[MediaDownloadStatus, str]
    file_path: str
    progress: int
    error_message: Optional[str]
    downloaded_bytes: Optional[int]
    format_downloaded: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class MediaDownloadAPIRead(_MediaDownloadAPIBaseOut):
    """Response body for a media download record."""

    created_at: datetime
    updated_at: datetime


class MediaDownloadAttemptAPIRead(ResponseBase):
    """One permanent entry in a download's attempt ledger."""

    id: int
    media_download_id: int
    is_redownload: bool
    status: Union[MediaDownloadStatus, str]
    error_message: Optional[str]
    downloaded_bytes: Optional[int]
    format_downloaded: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime


class MediaDownloadAPIReadView(MediaDownloadAPIRead):
    """A media download joined with its media item, parent context and profile."""

    # Generic identity of the actual item being downloaded. These remain useful
    # as additional media subtypes are added without making the UI infer the
    # downloaded item from its parent movie/show context.
    media_slug: Optional[str]
    media_title: Optional[str]

    episode_slug: Optional[str]
    episode_title: Optional[str]
    episode_identifier: Optional[str]
    show_slug: Optional[str]
    show_title: Optional[str]
    movie_slug: Optional[str]
    movie_title: Optional[str]
    local_media_profile_name: Optional[str]
    preferred_format: Optional[str]
    # Whether the most recent attempt was a redownload of an already-completed
    # file, and what publish_status that file was actually fetched at; both
    # None until the first attempt starts. Shown in the download's log.
    is_redownload_attempt: Optional[bool]
    downloaded_publish_status: Optional[str]
