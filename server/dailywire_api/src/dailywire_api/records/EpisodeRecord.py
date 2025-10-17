from __future__ import annotations

from typing import Any, Optional
from pydantic import (
    model_validator,
    AwareDatetime, Field, AliasPath,
)

from dailywire_api.records.BaseRecord import BaseRecord
from dailywire_api.utils.validators import ValOrNone


class EpisodeRecord(BaseRecord):

    dw_id: str = Field(validation_alias="id")
    slug: str
    title: str
    description: ValOrNone[str] = None
    duration: ValOrNone[float] = None

    media_type: ValOrNone[str] = None
    background_image: ValOrNone[str] = None
    sharing_url: ValOrNone[str] = None
    status: ValOrNone[str] = None
    is_downloadable: ValOrNone[bool] = None

    published_at: ValOrNone[AwareDatetime] = None
    scheduled_at: ValOrNone[AwareDatetime] = None

    thumbnail_landscape_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "land"), default=None)
    thumbnail_portrait_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "port"), default=None)
    thumbnail_square_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "square"), default=None)

    @model_validator(mode="before")
    @classmethod
    def normalize_data(cls, data: Any):
        if not isinstance(data, dict):
            return data

        if "showEpisode" in data and isinstance(data["showEpisode"], dict):
            data = data["showEpisode"]

        return data