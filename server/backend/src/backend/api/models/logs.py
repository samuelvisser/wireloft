from __future__ import annotations

from datetime import datetime

from backend.api.models.base import ResponseBase


class ApplicationLogEntryRead(ResponseBase):
    id: int
    timestamp: datetime
    level: str
    logger: str
    message: str
    exception: str | None = None


class ApplicationLogPageRead(ResponseBase):
    items: list[ApplicationLogEntryRead]
    total: int
    retained_limit: int
