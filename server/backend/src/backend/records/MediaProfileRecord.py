from __future__ import annotations

from pydantic import PastDatetime

from .BaseRecord import BaseRecord

class MediaProfileRecord(BaseRecord):
    id: str
    name: str
    output_template: str
    preferred_format: str
    download_series_images: bool = False
    created_date: PastDatetime
    modified_date: PastDatetime
