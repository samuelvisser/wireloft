from datetime import datetime
from typing import Optional

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus


# ---------- Strict input (create/update) ----------
class EpisodeDownloadAPICreate(RequestBase):
    """Request body for starting an episode download for a Local Media Profile."""

    local_media_profile_id: int


class MovieDownloadAPICreate(RequestBase):
    """Request body for starting a movie download for a Local Media Profile."""

    local_media_profile_id: int


class MediaDownloadAPIUpdate(RequestBase):
    """Update persistent artifact metadata only."""

    file_path: str


# ---------- Persistent artifact output ----------
class _MediaDownloadAPIBaseOut(ResponseBase):
    id: int
    type: str
    media_item_id: int
    local_media_profile_id: int
    file_path: str
    artifact_status: MediaDownloadArtifactStatus | str
    artifact_error: Optional[str]
    automatic_retry_suppressed: bool
    downloaded_bytes: Optional[int]
    format_downloaded: Optional[str]
    downloaded_at: Optional[datetime]


class MediaDownloadAPIRead(_MediaDownloadAPIBaseOut):
    """Persistent media artifact state. It never contains live task progress."""

    created_at: datetime
    updated_at: datetime


class MediaDownloadAttemptAPIRead(ResponseBase):
    """Immutable audit entry for one completed worker attempt."""

    id: int
    media_download_id: int
    is_redownload: bool
    status: str
    error_message: Optional[str]
    downloaded_bytes: Optional[int]
    format_downloaded: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime


class MediaDownloadAPIReadView(MediaDownloadAPIRead):
    """A persistent artifact joined with media/profile context and last attempt history."""

    media_slug: Optional[str]
    media_title: Optional[str]
    episode_slug: Optional[str]
    episode_title: Optional[str]
    episode_identifier: Optional[str]
    show_slug: Optional[str]
    show_title: Optional[str]
    movie_slug: Optional[str]
    movie_title: Optional[str]
    movie_extra_type: Optional[str]
    local_media_profile_name: Optional[str]
    preferred_format: Optional[str]
    downloaded_publish_status: Optional[str]

    # Historical facts from MediaDownloadAttempt. These are not live execution
    # state; they let an ordinary domain query explain why an absent artifact has
    # no file after the operation that produced the outcome is no longer active.
    latest_attempt_status: Optional[str]
    latest_attempt_error: Optional[str]
    latest_attempt_is_redownload: Optional[bool]
    latest_attempt_started_at: Optional[datetime]
    latest_attempt_finished_at: Optional[datetime]
