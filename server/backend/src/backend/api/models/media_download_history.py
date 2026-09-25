from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.api.models.base import ResponseBase


class MediaDownloadHistoryEntryRead(ResponseBase):
    id: int
    media_download_id: int
    action: str
    label: str
    status: str
    occurred_at: datetime
    duration_ms: int | None = None
    duration: str | None = None
    detail: str | None = None
    metadata: dict[str, Any]


class MediaDownloadHistoryPageRead(ResponseBase):
    items: list[MediaDownloadHistoryEntryRead]
    total: int
    offset: int
    limit: int
    has_more: bool
