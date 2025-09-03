from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check payload."""

    status: str = Field(default="ok", description="Service status indicator")


class ErrorResponse(BaseModel):
    """Standard error payload."""

    error: str


class MediaProfileItem(BaseModel):
    """Represents a media profile item returned by the API."""

    id: str
    name: str
    output_template: Optional[str] = None
    preferred_format: Optional[str] = None
    download_series_images: bool


class ShowItem(BaseModel):
    """Represents a show summary/detail item returned by the API."""

    id: str
    title: str
    author: str
    years: Optional[str] = None


class SettingItem(BaseModel):
    """Represents a single setting record."""

    slug: str
    name: str
    value: Optional[str] = None


class EpisodeItem(BaseModel):
    """Represents an episode summary/detail item returned by the API."""

    id: str
    title: str
    index: Optional[int] = None
    status: str = "downloaded"
