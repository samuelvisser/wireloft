from __future__ import annotations

from typing import Optional

from backend.api.models.response.response_base import ResponseModel


class MediaProfileItemResponse(ResponseModel):
    """Represents a media profile item returned by the API."""

    id: int
    slug: str
    name: str
    output_template: Optional[str] = None
    preferred_format: Optional[str] = None
    download_series_images: bool
