from __future__ import annotations

from datetime import datetime

from pydantic import computed_field

from backend.api.models.base import RequestBase, ResponseBase
from backend.utils.helpers import slugify


class MediaProfileAPIBase:
    """Fields common to all media profile models."""

    name: str
    output_template: str
    preferred_format: str
    download_series_images: bool


class MediaProfileAPICreate(MediaProfileAPIBase, RequestBase):
    """Request body for creating a media profile.
    Slug is generated automatically from the provided name.
    """

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return slugify(self.name)


class MediaProfileAPIRead(MediaProfileAPIBase, ResponseBase):
    """Response body for a media profile."""
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime


class MediaProfileAPIUpdate(MediaProfileAPIBase, RequestBase):
    """Request body for updating a media profile."""
    pass