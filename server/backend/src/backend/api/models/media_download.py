from datetime import datetime
from typing import Optional

from pydantic import AliasPath, Field

from backend.api.models.base import RequestBase, ResponseBase, response_model_config
from backend.types.download_profile_types import MediaDownloadArtifactStatus


# ---------- Strict input (create/update) ----------
class EpisodeDownloadAPICreate(RequestBase):
    """Request body for starting an episode download for a Local Media Profile."""

    local_media_profile_id: int
    redownload_when_final: bool = False


class MovieDownloadAPICreate(RequestBase):
    """Request body for starting a movie download for a Local Media Profile."""

    local_media_profile_id: int


class MediaDownloadAPIUpdate(RequestBase):
    """Update persistent artifact metadata only."""

    file_path: str


class MediaDownloadBulkActionAPIRequest(RequestBase):
    """Exact download rows selected by a Downloads-page bulk action."""

    media_download_ids: list[int]


# ---------- Persistent artifact output ----------
class _MediaDownloadAPIBaseOut(ResponseBase):
    model_config = response_model_config(nested_source="download")

    id: int
    type: str
    media_item_id: int
    local_media_profile_id: int
    file_path: str
    thumbnail_path: Optional[str] = None
    artifact_status: MediaDownloadArtifactStatus | str
    artifact_error: Optional[str]
    automatic_retry_suppressed: bool
    downloaded_bytes: Optional[int]
    format_downloaded: Optional[str]
    downloaded_at: Optional[datetime]
    redownload_when_final: Optional[bool] = None


class MediaDownloadAPIRead(_MediaDownloadAPIBaseOut):
    """Persistent media artifact state. It never contains live task progress."""

    created_at: datetime
    updated_at: datetime


class MediaDownloadAPIReadView(MediaDownloadAPIRead):
    """Persistent artifact context plus the latest canonical TaskRun facts."""

    media_slug: Optional[str] = Field(default=None, validation_alias=AliasPath("media", "slug"))
    media_title: Optional[str] = Field(default=None, validation_alias=AliasPath("media", "title"))
    episode_slug: Optional[str] = Field(default=None, validation_alias=AliasPath("episode", "slug"))
    episode_title: Optional[str] = Field(default=None, validation_alias=AliasPath("episode", "title"))
    episode_identifier: Optional[str] = Field(
        default=None,
        validation_alias=AliasPath("episode", "episode_identifier"),
    )
    show_slug: Optional[str] = Field(default=None, validation_alias=AliasPath("show", "slug"))
    show_title: Optional[str] = Field(default=None, validation_alias=AliasPath("show", "title"))
    movie_slug: Optional[str] = Field(default=None, validation_alias=AliasPath("movie", "slug"))
    movie_title: Optional[str] = Field(default=None, validation_alias=AliasPath("movie", "title"))
    movie_extra_type: Optional[str] = Field(
        default=None,
        validation_alias=AliasPath("movie_extra", "movie_extra_type"),
    )
    local_media_profile_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasPath("profile", "name"),
    )
    preferred_format: Optional[str] = Field(
        default=None,
        validation_alias=AliasPath("profile", "preferred_format"),
    )
    downloaded_publish_status: Optional[str] = Field(
        default=None,
        validation_alias=AliasPath("download", "downloaded_publish_status"),
    )

    queue_position: Optional[int] = None
    latest_task_status: Optional[str] = Field(
        default=None,
        validation_alias=AliasPath("latest_run", "status"),
    )
    latest_task_error: Optional[str] = Field(
        default=None,
        validation_alias=AliasPath("latest_run", "last_error"),
    )
    latest_task_is_redownload: Optional[bool] = None
    latest_task_started_at: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasPath("latest_run", "started_at"),
    )
    latest_task_finished_at: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasPath("latest_run", "finished_at"),
    )
