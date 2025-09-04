from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ShowItemResponse(BaseModel):
    """Represents a show summary/detail item returned by the API."""

    id: int
    slug: str
    title: str
    author_name: str
    years: Optional[str] = None
