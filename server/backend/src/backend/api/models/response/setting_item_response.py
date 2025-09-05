from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SettingItemResponse(BaseModel):
    """Represents a single setting record."""

    id: int
    slug: str
    name: str
    value: Optional[str] = None
