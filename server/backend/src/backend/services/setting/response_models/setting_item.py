from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SettingItem(BaseModel):
    """Represents a single setting record."""

    slug: str
    name: str
    value: Optional[str] = None
