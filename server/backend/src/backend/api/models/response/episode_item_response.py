from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class EpisodeItemResponse(BaseModel):
    """Represents an episode summary/detail item returned by the API."""

    id: int
    slug: str
    index: int
    title: str
    description: str
    unified_status: str
    index: Optional[int] = None
    went_live_date: Optional[str] = None
    published_date: Optional[str] = None
    downloaded_date: Optional[str] = None
    redownloaded_date: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def calculate_unified_status(cls, data: Any):
        """
        Use both publish_staus and download_status to calculate unified_status.
        """
        if isinstance(data, dict):
            if "publish_status" not in data or "download_status" not in data:
                return data

            if data["download_status"] is not None:
                data["unified_status"] = data["download_status"]
            else :
                data["unified_status"] = data["publish_status"]
        return data