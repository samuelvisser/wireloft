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


class MediaDownloadAPIReadView(MediaDownloadAPIRead):
    """A persistent artifact joined with media/profile context and latest TaskRun facts."""

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

    # Generic facts from the latest canonical download TaskRun. Full history is
    # served by /tasks/ledger rather than a MediaDownload-specific audit table.
    latest_task_status: Optional[str]
    latest_task_error: Optional[str]
    latest_task_is_redownload: Optional[bool]
    latest_task_started_at: Optional[datetime]
    latest_task_finished_at: Optional[datetime]
