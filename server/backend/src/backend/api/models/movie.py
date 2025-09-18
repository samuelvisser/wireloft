from __future__ import annotations

from typing import Optional
from datetime import datetime

from pydantic import computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.utils.helpers import generate_uuid


# ---------- Strict input (create/update) ----------
class _MovieAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    # Fields in the media_items table
    title: str
    description: Optional[str]
    downloaded_date: Optional[datetime]


class MovieAPICreate(_MovieAPIBaseIn):
    """Request body for creating a movie."""

    # Fields in the media_items table
    dw_id: Optional[str] = None
    slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class MovieAPIUpdate(_MovieAPIBaseIn):
    """Request body for updating a movie."""
    pass


# ---------- Lenient output (read) ----------
class _MovieAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    # Fields in the media_items table
    id: int
    uuid: str
    dw_id: Optional[str] = None
    slug: str
    title: str
    description: Optional[str]
    downloaded_date: Optional[datetime]


class MovieAPIRead(_MovieAPIBaseOut):
    """Represents a movie summary/detail item returned by the API."""

    created_at: datetime
    updated_at: datetime