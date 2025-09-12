from __future__ import annotations

from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    """Health check payload."""

    status: str = Field(default="ok", description="Service status indicator")
