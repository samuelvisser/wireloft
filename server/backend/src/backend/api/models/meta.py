from __future__ import annotations

from pydantic import Field

from backend.api.models.base import ResponseBase


class HealthAPIRead(ResponseBase):
    """Health check payload."""

    status: str = Field(default="ok", description="Service status indicator")
