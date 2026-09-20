from __future__ import annotations

from typing import Annotated, Union

from pydantic import AliasPath, Field

from backend.api.models.download_profile import DownloadProfileAPIRead
from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPIRead
from backend.api.models.series_download_profile import SeriesDownloadProfileAPIRead


DownloadProfileImplementation = Annotated[
    Union[PodcastDownloadProfileAPIRead, SeriesDownloadProfileAPIRead],
    Field(discriminator="type"),
]


class DownloadProfileAPIReadView(DownloadProfileAPIRead):
    """Denormalized download-profile view sourced from ORM relationships."""

    show_title: str = Field(validation_alias=AliasPath("profile", "show", "title"))
    show_slug: str = Field(validation_alias=AliasPath("profile", "show", "slug"))
    local_media_profile_name: str = Field(
        validation_alias=AliasPath("profile", "local_media_profile", "name")
    )
    local_media_profile_preferred_format: str = Field(
        validation_alias=AliasPath("profile", "local_media_profile", "preferred_format")
    )
    download_profile_impl: DownloadProfileImplementation = Field(
        validation_alias="profile"
    )
