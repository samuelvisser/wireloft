from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


class _SeasonAPIBase:
    """Fields common to all season models."""
    name: str


class SeasonAPICreate(_SeasonAPIBase, RequestBase):
    """Request body for creating a season."""
    dw_id: str
    show_id: str
    slug: str


class SeasonAPIRead(_SeasonAPIBase, ResponseBase):
    """Response body for a season."""
    id: int
    dw_id: str
    show_id: str
    slug: str
    created_at: datetime
    updated_at: datetime


class SeasonAPIUpdate(_SeasonAPIBase, RequestBase):
    """Request body for updating a season."""
    pass