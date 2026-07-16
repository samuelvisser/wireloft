from __future__ import annotations

from typing import Any, Optional
from pydantic import (
    model_validator,
    AwareDatetime, Field, AliasPath,
)

from dailywire_api.records.BaseRecord import BaseRecord
from dailywire_api.types.user_info import DwMembershipLevel
from dailywire_api.utils.validators import ValOrNone, ValOrZero, ValOrEmpty, AvailableForList


class DwEpisodeRecord(BaseRecord):

    dw_id: str = Field(validation_alias="id")
    slug: str
    title: str
    description: ValOrNone[str] = None
    duration: ValOrZero[float]

    # Episode numbering, straight from Daily Wire's API. `episode_number` is a string
    # like "2460.10": the whole part is the episode number, the fractional part is a
    # segment/variant (.00 = main episode, .10 = memberblock, .20 = other extra, ...).
    # `display_episode_number` is Daily Wire's own presentation string (e.g. "Ep. 2324"
    # or "" when they don't want to show one).
    episode_number: ValOrEmpty = ""
    display_episode_number: ValOrEmpty = ""

    background_image_path: ValOrNone[str] = Field(validation_alias="backgroundImage", default=None)
    sharing_url: str
    publish_status: str = Field(validation_alias="status")
    is_downloadable: bool

    has_free_and_paid_video: bool = False
    is_paid_video: bool = False

    available_for: AvailableForList = Field(default_factory=list)

    thumbnail_landscape_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "land"), default=None)
    thumbnail_portrait_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "port"), default=None)
    thumbnail_square_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "square"), default=None)

    published_date: AwareDatetime = Field(validation_alias="publishedAt")
    scheduled_date: Optional[AwareDatetime] = Field(validation_alias="scheduledAt", default=None)

    @property
    def ep_number(self) -> Optional[int]:
        """The whole-number episode number parsed from `episode_number`.

        "2460.10" -> 2460, "2324" -> 2324. Returns None when Daily Wire provides no
        usable number (empty or non-numeric), so callers can fall back explicitly.
        """
        raw = self.episode_number.strip()
        if not raw:
            return None
        try:
            return int(raw.split(".", 1)[0])
        except ValueError:
            return None

    @property
    def ep_segment(self) -> int:
        """The segment/variant parsed from the fractional part of `episode_number`.

        "2460.10" -> 10, "2462.20" -> 20, "2460"/"2460.00" -> 0.
        """
        raw = self.episode_number.strip()
        if "." not in raw:
            return 0
        try:
            return int(raw.split(".", 1)[1])
        except ValueError:
            return 0

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
        return isinstance(other, DwEpisodeRecord) and self.slug == other.slug

    def __hash__(self) -> int:
        return hash(self.slug)