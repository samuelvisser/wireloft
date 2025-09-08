from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class EpisodeItemResponse(BaseModel):
    """Represents an episode summary/detail item returned by the API."""

    id: int
    slug: str
    index: int
    title: str
    description: str
    status: str
    index: Optional[int] = None
    status: str
    went_live_date: Optional[str] = None
    published_date: Optional[str] = None
    downloaded_date: Optional[str] = None
    redownloaded_date: Optional[str] = None
