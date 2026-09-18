from __future__ import annotations

from typing import Generic, TypeVar

from backend.api.models.base import ResponseBase


T = TypeVar("T")


class OffsetPageRead(ResponseBase, Generic[T]):
    """Reusable offset-paginated API response for lazily loaded collections."""

    items: list[T]
    offset: int
    limit: int
    has_more: bool
