from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


# ---------- Strict input (create/update) ----------
class _SeasonAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    name: str


class SeasonAPIRequestDetached(_SeasonAPIBaseIn):
    """Request body without external relations, allowing for dynamic insertion"""

    slug: str


class SeasonAPICreate(_SeasonAPIBaseIn):
    """Request body for creating a season."""

    show_id: int
    index: int
    slug: str


class SeasonAPIUpdate(_SeasonAPIBaseIn):
    """Request body for updating a season."""

    index: int


# ---------- Lenient output (read) ----------
class _SeasonAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""
    id: int
    show_id: int
    index: int
    name: str
    slug: str


class SeasonAPIRead(_SeasonAPIBaseOut):
    """Response body for a season."""
    created_at: datetime
    updated_at: datetime




