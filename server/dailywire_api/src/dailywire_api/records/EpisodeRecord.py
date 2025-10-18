from __future__ import annotations

from typing import Any
from pydantic import (
    model_validator,
    AwareDatetime, Field, AliasPath,
)

from dailywire_api.records.BaseRecord import BaseRecord
from dailywire_api.types.user_info import DwMembershipLevel
from dailywire_api.utils.validators import ValOrNone, ValOrZero, AvailableForList


class EpisodeRecord(BaseRecord):

    dw_id: str = Field(validation_alias="id")
    slug: str
    title: str
    description: str
    duration: ValOrZero[float]

    background_image_path: ValOrNone[str] = Field(validation_alias="backgroundImage", default=None)
    sharing_url: str
    publish_status: str = Field(validation_alias="status")
    is_downloadable: bool

    available_for: AvailableForList

    thumbnail_landscape_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "land"), default=None)
    thumbnail_portrait_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "port"), default=None)
    thumbnail_square_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "square"), default=None)

    published_date: AwareDatetime = Field(validation_alias="publishedAt")
    scheduled_date: AwareDatetime = Field(validation_alias="scheduledAt")

    @property
    def is_member_exclusive(self) -> bool:
        paid = {DwMembershipLevel.INSIDER, DwMembershipLevel.INSIDER_PLUS, DwMembershipLevel.ALL_ACCESS}
        return not DwMembershipLevel.FREE in self.available_for and any(t in paid for t in self.available_for)

    @model_validator(mode="before")
    @classmethod
    def normalize_data(cls, data: Any):
        if not isinstance(data, dict):
            return data

        if "showEpisode" in data and isinstance(data["showEpisode"], dict):
            data = data["showEpisode"]

        return data

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EpisodeRecord) and self.slug == other.slug

    def __hash__(self) -> int:
        return hash(self.slug)