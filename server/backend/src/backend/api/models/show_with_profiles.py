from __future__ import annotations
from typing import Literal, Union
from pydantic import Field

from backend.api.models.base import RequestBase
from backend.api.models.download_profile_series import DownloadProfileSeriesAPICreate
from backend.api.models.media_profile import MediaProfileAPICreate, MediaProfileAPIUpdate
from backend.api.models.download_profile_podcast import DownloadProfilePodcastAPICreate
from backend.api.models.show import ShowAPICreate


class MediaProfileCreateNew(RequestBase):
    op: Literal["create_new"] = "create_new"
    create: MediaProfileAPICreate


class MediaProfileUpdateBySlug(RequestBase):
    op: Literal["update_by_slug"] = "update_by_slug"
    slug: str
    update: MediaProfileAPIUpdate


MediaProfileAPIUpsert = Union[
    MediaProfileCreateNew,
    MediaProfileUpdateBySlug,
]


class ShowAPICreateBundle(RequestBase):
    show: ShowAPICreate
    download_profile: Union[
        DownloadProfilePodcastAPICreate,
        DownloadProfileSeriesAPICreate
    ]
    media_profile: MediaProfileAPIUpsert = Field(discriminator="op")
