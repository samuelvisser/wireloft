from __future__ import annotations

from typing import Optional

from pydantic import AwareDatetime, computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.utils.helpers import generate_uuid


class MovieAPIBase:
    """Fields common to all movie models."""

    # Fields in the media_items table
    title: str
    description: Optional[str]
    downloaded_date: Optional[AwareDatetime]


class MovieAPICreate(MovieAPIBase, RequestBase):
    """Request body for creating a movie."""

    # Fields in the media_items table
    dw_id: Optional[str] = None
    slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class MovieAPIRead(MovieAPIBase, ResponseBase):
    """Represents a movie summary/detail item returned by the API."""

    # Fields in the media_items table
    id: int
    uuid: str
    dw_id: Optional[str] = None
    slug: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class MovieAPIUpdate(MovieAPIBase, RequestBase):
    """Request body for updating a movie."""
    pass
