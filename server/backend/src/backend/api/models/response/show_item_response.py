from __future__ import annotations

from typing import Optional

from backend.api.models.response.response_base import ResponseModel


class ShowItemResponse(ResponseModel):
    """Represents a show summary/detail item returned by the API."""

    id: int
    slug: str
    media_profile_id: int
    title: str
    description: str
    url: str
    author_name: str
    author_headshot_path: Optional[str] = None
    download_media: bool
    download_delay_minutes: int
    redownload_delay_minutes: int
    download_days_in_past: int
    delete_older_episodes: bool
    title_filter: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None
    years: Optional[str] = None
