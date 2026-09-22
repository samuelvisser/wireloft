from __future__ import annotations
from typing import Literal, Union, Optional
from pydantic import Field

from backend.api.models.base import RequestBase
from backend.api.models.series_download_profile import SeriesDownloadProfileAPICreateBundle
from backend.api.models.show_local_media_profile import (
    ShowLocalMediaProfileAPICreate,
    ShowLocalMediaProfileAPIUpdate,
)
from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPICreateBundle
from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate
from backend.api.models.season import SeasonAPIRequestDetached
from backend.api.models.show import ShowAPICreate


class ShowLocalMediaProfileCreateNew(ShowLocalMediaProfileAPICreate):
    op: Literal["create_new"] = "create_new"


class ShowLocalMediaProfileUpdateBySlug(ShowLocalMediaProfileAPIUpdate):
    op: Literal["update_by_slug"] = "update_by_slug"
    slug_selector: str = Field(validation_alias="slug")


ShowLocalMediaProfileAPIUpsert = Union[
    ShowLocalMediaProfileCreateNew,
    ShowLocalMediaProfileUpdateBySlug,
]


class PodcastDownloadProfileCreateInBundle(PodcastDownloadProfileAPICreateBundle):
    op: Literal["podcast"] = "podcast"


class SeriesDownloadProfileCreateInBundle(SeriesDownloadProfileAPICreateBundle):
    op: Literal["series"] = "series"


DownloadProfileCreateInBundle = Union[
    PodcastDownloadProfileCreateInBundle,
    SeriesDownloadProfileCreateInBundle,
]


class RssStreamProfileCreateInBundle(RssStreamProfileAPICreate):
    show_id: Optional[int] = None


class ShowAPICreateBundle(RequestBase):
    show: ShowAPICreate
    seasons: list[SeasonAPIRequestDetached]
    local_media_profile: Optional[ShowLocalMediaProfileAPIUpsert] = Field(default=None, discriminator="op")
    download_profile: Optional[DownloadProfileCreateInBundle] = Field(default=None, discriminator="op")
    stream_profile: Optional[RssStreamProfileCreateInBundle] = None
