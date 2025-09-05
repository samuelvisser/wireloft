from __future__ import annotations

from typing import Optional

from backend.api.models.response.response_base import ResponseModel


class ShowItemResponse(ResponseModel):
    """Represents a show summary/detail item returned by the API."""

    id: int
    slug: str
    title: str
    author_name: str
    years: Optional[str] = None
