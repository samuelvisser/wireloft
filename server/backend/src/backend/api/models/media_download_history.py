from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.api.models.base import ResponseBase


class MediaDownloadHistoryEntryRead(ResponseBase):
    """One normalized entry in a media download's user-facing history."""

    key: str
    status: str
    activity: str
    occurred_at: Optional[datetime]
    error: Optional[str]


class MediaDownloadHistoryPageRead(ResponseBase):
    items: list[MediaDownloadHistoryEntryRead]
    total: int
    offset: int
    limit: int
    has_more: bool
