from __future__ import annotations

from typing import Literal

from backend.api.models.base import ResponseBase
from backend.api.models.media_download import MediaDownloadAPIReadView
from backend.api.models.operations import TaskOperationRead


class FrontendPullData(ResponseBase):
    """Typed payloads delivered through the single frontend polling pipeline."""

    operations: list[TaskOperationRead]
    media_downloads: list[MediaDownloadAPIReadView]


class FrontendPullAPIRead(ResponseBase):
    """One frontend polling snapshot and the cadence it should use next."""

    mode: Literal["slow", "fast"]
    data: FrontendPullData
