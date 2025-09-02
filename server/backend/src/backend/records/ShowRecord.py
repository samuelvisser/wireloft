from __future__ import annotations

from typing import Optional
from pydantic import PastDatetime

from .BaseRecord import BaseRecord


class ShowRecord(BaseRecord):
    id: str
    uuid: str
    dw_id: str
    slug: str
    title: str
    description: Optional[str] = None
    url: str
    status: str
    media_type: str
    author_name: str
    author_slug: str
    author_headshot_path: Optional[str] = None
    download_media: int = 0
    download_delay_minutes: int = 0
    redownload_delay_minutes: int = 0
    download_days_in_past: int = 0
    delete_older_episodes: int = 0
    title_filter: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None
    created_date: PastDatetime
    modified_date: PastDatetime
