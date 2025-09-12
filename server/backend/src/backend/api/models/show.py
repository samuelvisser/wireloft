from typing import Optional

from pydantic import AwareDatetime

from backend.api.models.base import RequestBase, ResponseBase


class ShowAPIBase:
    """Fields common to all show models."""
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


class ShowAPICreate(ShowAPIBase, RequestBase):
    """Request body for creating a show."""
    slug: str = ""


class ShowAPIRead(ShowAPIBase, ResponseBase):
    """Response body for a show."""

    id: int
    slug: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ShowAPIUpdate(ShowAPIBase, RequestBase):
    """Request body for updating a show."""
    pass