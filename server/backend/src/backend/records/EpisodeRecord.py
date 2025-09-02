from __future__ import annotations

from typing import Optional
from pydantic import PastDatetime

from .BaseRecord import BaseRecord


class EpisodeRecord(BaseRecord):
    id: str  # prefer slug where available; otherwise stringified numeric id
    show_id: int
    uuid: str
    dw_id: str
    slug: str
    title: str
    description: Optional[str] = None
    status: str
    went_live_date: Optional[PastDatetime] = None
    published_date: Optional[PastDatetime] = None
    downloaded_date: Optional[PastDatetime] = None
    redownloaded_date: Optional[PastDatetime] = None
    created_date: PastDatetime
    modified_date: PastDatetime
