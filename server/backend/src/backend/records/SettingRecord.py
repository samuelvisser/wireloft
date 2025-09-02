from __future__ import annotations

from typing import Optional
from pydantic import PastDatetime

from .BaseRecord import BaseRecord


class SettingRecord(BaseRecord):
    id: int
    slug: str
    name: str
    value: Optional[str] = None
    created_date: PastDatetime
    modified_date: PastDatetime
