from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class EpisodeItem(BaseModel):
    """Represents an episode summary/detail item returned by the API."""

    id: str
    title: str
    index: Optional[int] = None
    status: str = "downloaded"
