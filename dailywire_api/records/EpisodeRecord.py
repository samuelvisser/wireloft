from typing import Any
import re
from pydantic import (
    ConfigDict,
    model_validator,
    AliasChoices,
    AwareDatetime,
)

from dailywire_api.records.BaseRecord import BaseRecord
from dailywire_api.records.ThumbnailRecord import ThumbnailRecord


class EpisodeRecord(BaseRecord):
    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
    )

    id: str
    slug: str
    title: str
    description: str | None = None
    duration: float | int | None = None

    media_type: str | None = None
    background_image: str | None = None
    sharing_url: str | None = None
    parent_title: str | None = None
    status: str | None = None
    episode_number: int | None = None

    published_at: AwareDatetime | None = None
    scheduled_at: AwareDatetime | None = None

    thumbnail: ThumbnailRecord | None = None



    @model_validator(mode="before")
    @classmethod
    def _unwrap_and_lift(cls, data: Any):
        if not isinstance(data, dict):
            return data

        # Unwrap the common wrapper shape: {"showEpisode": {...}}
        if "showEpisode" in data and isinstance(data["showEpisode"], dict):
            data = data["showEpisode"]
        return data


    @model_validator(mode="before")
    @classmethod
    def lift_thumbnail(cls, data: Any):
        """
        Accept raw API episode (with images.thumbnail.*) or already-slim dict.
        Normalize images.thumbnail -> thumbnail.
        """
        if isinstance(data, dict):
            if "thumbnail" not in data:
                images = data.get("images") or {}
                thumb = images.get("thumbnail")
                if isinstance(thumb, dict):
                    data = {**data, "thumbnail": thumb}
        return data

    @model_validator(mode="before")
    @classmethod
    def compute_episode_number(cls, data: Any):
        """
        Prefer the API-provided episodeNumber if present and non-empty; otherwise
        parse the title for 'EP.' followed by an integer, case-insensitive.
        Example: 'Ep. 2268 - BOMBSHELL' -> 2268
        """
        if not isinstance(data, dict):
            return data

        # Normalize existing API value if provided
        ep_number = data.get("episodeNumber", None)
        if isinstance(ep_number, str):
            s = ep_number.strip()

            if s == "":
                ep_number = None
            elif s.isdigit():
                try:
                    ep_number = int(s)
                    return {**data, "episodeNumber": ep_number}
                except Exception:
                    ep_number = None



        # Fallback: parse from title if possible
        title = data.get("title")

        print(title)


        if isinstance(title, str):
            m = re.search(r"\bEp\.\s*(\d+)", title, flags=re.IGNORECASE)
            if m:
                try:
                    parsed = int(m.group(1))

                    print(parsed)

                    return {**data, "episodeNumber": parsed}
                except Exception:
                    pass

        if isinstance(ep_number, str) and ep_number.strip() == "":
            return {**data, "episodeNumber": None}

        # Nothing parsed; leave as-is (field will default to None)
        return data