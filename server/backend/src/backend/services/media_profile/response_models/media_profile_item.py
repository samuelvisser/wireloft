from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MediaProfileItem(BaseModel):
    """Represents a media profile item returned by the API."""

    id: str
    name: str
    output_template: Optional[str] = None
    preferred_format: Optional[str] = None
    download_series_images: bool
