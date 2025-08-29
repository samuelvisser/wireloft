from typing import Any

from pydantic import BaseModel, Field, ConfigDict, AwareDatetime, AliasChoices, model_validator, field_validator

from pydantic.alias_generators import to_camel

from dailywire_api.records.EpisodeRecord import EpisodeRecord
from dailywire_api.records.SeasonRecord import SeasonRecord
from dailywire_api.records.BaseRecord import BaseRecord
from dailywire_api.records.ThumbnailRecord import ThumbnailRecord


class ShowRecord(BaseRecord):
    """
    Minimal, app-friendly 'Show' record.
    We accept either:
      - a full ShowPage payload (with top-level 'show' and 'selectedSeason'), OR
      - an already-slim dict in this model's shape.
    """
    model_config = ConfigDict(
        frozen=True,                 # treat as immutable
        extra="ignore",
        populate_by_name=True,
        alias_generator=to_camel,    # camelCase on output if you use by_alias=True
    )

    id: str
    slug: str
    title: str
    description: str | None = None
    media_type: str | None = Field(default=None)

    author_name: str | None = Field(default=None)
    author_slug: str | None = Field(default=None)
    author_headshot: str | None = Field(default=None)

    background_image: str | None = Field(default=None)
    logo_image: str | None = Field(default=None)
    sharing_url: str | None = Field(default=None)
    thumbnail: ThumbnailRecord | None = None

    latest_season: SeasonRecord | None = None
    seasons: list[SeasonRecord] = Field(default_factory=list)

    latest_episode: EpisodeRecord | None = None
    latest_episodes: list[EpisodeRecord] = Field(default_factory=list)


    @model_validator(mode="before")
    @classmethod
    def _from_show_page(cls, data: Any):
        """
        If given a ShowPage payload, normalize to this model's shape.
        Otherwise (already normalized), return as-is.
        """
        if not isinstance(data, dict):
            return data

        # Detect the ShowPage envelope
        if "show" in data and isinstance(data["show"], dict):
            s = data["show"]
            a = s.get("author") or {}
            images = s.get("images") or {}
            thumb = images.get("thumbnail")

            # Collect episodes from: tabs[].components[].items[].showEpisode
            eps: list[dict[str, Any]] = []
            for tab in data.get("tabs", []) or []:
                for comp in tab.get("components", []) or []:
                    for item in comp.get("items", []) or []:
                        se = item.get("showEpisode") if isinstance(item, dict) else None
                        if isinstance(se, dict):
                            eps.append(se)

            return {
                # core
                "id": s.get("id"),
                "slug": s.get("slug"),
                "title": s.get("title"),
                "description": s.get("description"),

                # flattened author
                "author_name": a.get("name"),
                "author_slug": a.get("slug"),
                "author_headshot": a.get("headshot"),

                # images / media
                "background_image": s.get("backgroundImage") or s.get("background_image"),
                "logo_image": s.get("logoImage") or s.get("logo_image"),
                "media_type": s.get("mediaType") or s.get("media_type"),
                "sharing_url": s.get("sharingURL") or s.get("sharing_url"),

                # nested blocks
                "thumbnail": thumb,
                "latest_season": data.get("selectedSeason"),
                "seasons": s.get("seasons") or [],

                # episodes (raw dicts; EpisodeRecord will normalize/validate)
                "latest_episode":  s.get("latestEpisode"),
                "latest_episodes": eps,
            }

        # Already in ShowRecord shape? let normal validation handle it.
        return data