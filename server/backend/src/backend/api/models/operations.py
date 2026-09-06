from __future__ import annotations

from typing import Any, Optional

from backend.api.models.base import ResponseBase


class TaskOperationAccepted(ResponseBase):
    queued: bool
    operation_id: str


class MediaDownloadOperationAccepted(TaskOperationAccepted):
    media_download_id: int


class ShowMetadataOperationAccepted(TaskOperationAccepted):
    episodes_queued: int


class ShowFileRenameOperationAccepted(TaskOperationAccepted):
    episodes_queued: int
    download_profiles_queued: int


class LocalMediaProfileFileRenameOperationAccepted(TaskOperationAccepted):
    episodes_queued: int


class ShowRedownloadOperationAccepted(TaskOperationAccepted):
    download_profiles_queued: int


class EpisodeMetadataOperationAccepted(TaskOperationAccepted):
    episode_id: int


class TaskOperationRead(ResponseBase):
    id: str
    kind: str
    source: str
    resource_type: str
    resource_id: Optional[int]
    title: str
    status: str
    progress: Optional[int]
    progress_current: int
    progress_total: int
    message: Optional[str]
    result: Optional[dict[str, Any]]
    context: Optional[dict[str, Any]]
    error: Optional[str]
    notification_seen_at: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
