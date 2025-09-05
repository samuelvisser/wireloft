from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class EpisodeItemResponse(BaseModel):
    """Represents an episode summary/detail item returned by the API."""

    id: int
    slug: str
    title: str
    index: Optional[int] = None
    status: str
