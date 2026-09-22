from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from backend.api.models.base import ResponseBase
from backend.api.models.tasks import TaskLedgerEntryRead
from backend.types.download_profile_types import MediaDownloadArtifactStatus


class MediaDownloadTaskHistoryEntryRead(TaskLedgerEntryRead):
    """A canonical download TaskRun projected into download history."""

    source: Literal["task"] = "task"


class MediaDownloadArtifactHistoryEntryRead(ResponseBase):
    """Current problem state discovered by artifact reconciliation."""

    source: Literal["artifact"] = "artifact"
    artifact_status: MediaDownloadArtifactStatus | str
    artifact_error: Optional[str]
    file_path: str
    observed_at: datetime = Field(validation_alias="updated_at")


MediaDownloadHistoryEntryRead = Annotated[
    Union[MediaDownloadTaskHistoryEntryRead, MediaDownloadArtifactHistoryEntryRead],
    Field(discriminator="source"),
]


class MediaDownloadHistoryPageRead(ResponseBase):
    items: list[MediaDownloadHistoryEntryRead]
    total: int
    offset: int
    limit: int
    has_more: bool
