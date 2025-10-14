from __future__ import annotations
from typing import Literal, Union, Optional
from pydantic import Field

from backend.api.models.base import RequestBase
from backend.api.models.series_download_profile import SeriesDownloadProfileAPICreateBundle
from backend.api.models.local_media_profile import LocalMediaProfileAPICreate, LocalMediaProfileAPIUpdate
from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPICreateBundle
from backend.api.models.season import SeasonAPIRequestDetached
from backend.api.models.show import ShowAPICreate


class LocalMediaProfileCreateNew(LocalMediaProfileAPICreate):
    op: Literal["create_new"] = "create_new"


class LocalMediaProfileUpdateBySlug(LocalMediaProfileAPIUpdate):
    op: Literal["update_by_slug"] = "update_by_slug"
    slug_selector: str = Field(validation_alias="slug")


LocalMediaProfileAPIUpsert = Union[
    LocalMediaProfileCreateNew,
    LocalMediaProfileUpdateBySlug,
]


# Download profile inputs for bundle (no IDs yet, include discriminator)
class PodcastDownloadProfileCreateInBundle(PodcastDownloadProfileAPICreateBundle):
    op: Literal["podcast"] = "podcast"


class SeriesDownloadProfileCreateInBundle(SeriesDownloadProfileAPICreateBundle):
    op: Literal["series"] = "series"


DownloadProfileCreateInBundle = Union[
    PodcastDownloadProfileCreateInBundle,
    SeriesDownloadProfileCreateInBundle,
]


class ShowAPICreateBundle(RequestBase):
    show: ShowAPICreate
    download_profile: DownloadProfileCreateInBundle = Field(discriminator="op")
    local_media_profile: LocalMediaProfileAPIUpsert = Field(discriminator="op")
    seasons: list[SeasonAPIRequestDetached]
