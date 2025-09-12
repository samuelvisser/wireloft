from __future__ import annotations
from typing import Optional, Annotated, Literal, Union
from pydantic import BaseModel, Field, model_validator

from backend.api.models.base import RequestBase
from backend.api.models.media_profile import MediaProfileAPICreate, MediaProfileAPIUpdate
from backend.api.models.download_profile import DownloadProfileAPICreate
from backend.api.models.show import ShowAPICreate


class MediaProfileCreateNew(MediaProfileAPICreate):
    op: Literal["create_new"] = "create_new"


class MediaProfileUpdateBySlug(MediaProfileAPIUpdate):
    op: Literal["update_by_slug"] = "update_by_slug"
    slug: str  # key to find-or-create


MediaProfileAPIUpsert = Union[
    MediaProfileCreateNew,
    MediaProfileUpdateBySlug,
]


class ShowAPICreateBundle(RequestBase):
    show: ShowAPICreate
    download_profile: DownloadProfileAPICreate
    media_profile: MediaProfileAPIUpsert = Field(discriminator="op")
