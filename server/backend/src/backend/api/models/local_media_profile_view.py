from __future__ import annotations

from typing import Annotated

from pydantic import Field

from backend.api.models.base import ResponseBase
from backend.api.models.movie_local_media_profile import MovieLocalMediaProfileAPIRead
from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPIRead


LocalMediaProfileAPIRead = Annotated[
    ShowLocalMediaProfileAPIRead | MovieLocalMediaProfileAPIRead,
    Field(discriminator="type"),
]


class LocalMediaProfileStatisticsAPIRead(ResponseBase):
    managed_media_count: int
    downloaded_media_count: int
    storage_size_bytes: int
    download_profile_count: int


class LocalMediaProfileViewAPIRead(ResponseBase):
    profile: LocalMediaProfileAPIRead
    statistics: LocalMediaProfileStatisticsAPIRead
