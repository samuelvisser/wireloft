from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ShowItem(BaseModel):
    """Represents a show summary/detail item returned by the API."""

    id: str
    title: str
    author: str
    years: Optional[str] = None
