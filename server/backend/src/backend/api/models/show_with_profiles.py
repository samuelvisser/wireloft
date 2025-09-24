from __future__ import annotations
from typing import Literal, Union, Optional
from pydantic import Field

from backend.api.models.base import RequestBase
from backend.api.models.download_profile_series import DownloadProfileSeriesAPICreateBundle
from backend.api.models.media_profile import MediaProfileAPICreate, MediaProfileAPIUpdate
from backend.api.models.download_profile_podcast import DownloadProfilePodcastAPICreateBundle
from backend.api.models.show import ShowAPICreate


class MediaProfileCreateNew(MediaProfileAPICreate):
    op: Literal["create_new"] = "create_new"


class MediaProfileUpdateBySlug(MediaProfileAPIUpdate):
    op: Literal["update_by_slug"] = "update_by_slug"


MediaProfileAPIUpsert = Union[
    MediaProfileCreateNew,
    MediaProfileUpdateBySlug,
]


# Download profile inputs for bundle (no IDs yet, include discriminator)
class DownloadProfilePodcastCreateInBundle(DownloadProfilePodcastAPICreateBundle):
    op: Literal["podcast"] = "podcast"


class DownloadProfileSeriesCreateInBundle(DownloadProfileSeriesAPICreateBundle):
    op: Literal["series"] = "series"


DownloadProfileCreateInBundle = Union[
    DownloadProfilePodcastCreateInBundle,
    DownloadProfileSeriesCreateInBundle,
]


class ShowAPICreateBundle(RequestBase):
    show: ShowAPICreate
    download_profile: DownloadProfileCreateInBundle = Field(discriminator="op")
    media_profile: MediaProfileAPIUpsert = Field(discriminator="op")
