from __future__ import annotations

from typing import Literal

from backend.api.models.base import ResponseBase
from backend.api.models.operations import TaskOperationRead


class FrontendPullData(ResponseBase):
    """Live execution state delivered through the single frontend polling pipeline."""

    operations: list[TaskOperationRead]


class FrontendPullAPIRead(ResponseBase):
    """One generic execution snapshot and the cadence the frontend should use next."""

    mode: Literal["slow", "fast"]
    data: FrontendPullData
