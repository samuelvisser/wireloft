from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import computed_field

from backend.api.models.base import ResponseBase


T = TypeVar("T")


class OffsetPageRead(ResponseBase, Generic[T]):
    """Reusable offset-paginated API response for lazily loaded collections."""

    items: list[T]
    offset: int
    limit: int
    has_more: bool



class CursorPageRead(ResponseBase, Generic[T]):
    """Reusable cursor-paginated API response for changing ordered collections."""

    items: list[T]
    limit: int
    next_cursor: str | None = None
    previous_cursor: str | None = None
    revision: str | None = None

    @computed_field(return_type=bool)
    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None

    @computed_field(return_type=bool)
    @property
    def has_previous(self) -> bool:
        return self.previous_cursor is not None
