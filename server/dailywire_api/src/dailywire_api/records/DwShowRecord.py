from typing import Any
from enum import Enum

from pydantic import Field, model_validator, computed_field, AliasPath

from dailywire_api.records.BaseRecord import BaseRecord
from dailywire_api.records.DwEpisodeRecord import DwEpisodeRecord
from dailywire_api.records.DwSeasonRecord import DwSeasonRecord
from dailywire_api.utils.validators import ValOrNone


class ProbableShowType(str, Enum):
    unknown = "unknown"
    podcast = "podcast"
    series = "series"

class ProbableEpisodeIdentification(str, Enum):
    unknown = "unknown"
    date_based = "date_based"
    numbered = "numbered"


class DwShowRecord(BaseRecord):
    """
    Minimal, app-friendly 'Show' record.
    We accept either:
      - a full ShowPage payload (with top-level 'show' and 'selectedSeason'), OR
      - an already-slim dict in this model's shape.
    """

    dw_id: str = Field(validation_alias="id")
    slug: str
    title: str
    description: ValOrNone[str] = Field(default=None)
    background_image_path: ValOrNone[str] = Field(validation_alias="backgroundImage", default=None)
    logo_image_path: ValOrNone[str] = Field(validation_alias="logoImage", default=None)
    sharing_url: str

    author_name: ValOrNone[str] = Field(validation_alias=AliasPath("author", "name"), default=None)
    author_slug: ValOrNone[str] = Field(validation_alias=AliasPath("author", "slug"), default=None)
    author_headshot_path: ValOrNone[str] = Field(validation_alias=AliasPath("author", "headshot"), default=None)

    thumbnail_landscape_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "land"), default=None)
    thumbnail_portrait_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "port"), default=None)
    thumbnail_square_path: ValOrNone[str] = Field(validation_alias=AliasPath("images", "thumbnail", "square"), default=None)

    latest_season: DwSeasonRecord
    seasons: list[DwSeasonRecord] = Field(default_factory=list)

    latest_episode: DwEpisodeRecord
    latest_episodes: list[DwEpisodeRecord] = Field(default_factory=list)


    @computed_field(return_type=ProbableShowType)
    @property
    def probable_show_type(self) -> ProbableShowType:
        """
        Determine probable show type based on latest_episodes.
        """
        # Podcast if all seasons are year-labeled between 2015 and 2115
        seasons_list = [s for s in (self.seasons or []) if isinstance(s, DwSeasonRecord)]
        if seasons_list and all(isinstance(s.name, str) and len(s.name) == 4 and s.name.isdigit() and 2015 <= int(s.name) <= 2115 for s in seasons_list):
            return ProbableShowType.podcast

        # Podcast if the slug contains the literal word "podcast"
        if "podcast" in self.slug.lower():
            return ProbableShowType.podcast

        # Unknown if fewer than 5 episodes
        total = len(self.latest_episodes or [])
        if total <= 5:
            return ProbableShowType.unknown

        # Podcast if >= 40% of episode titles contain the exact substring "Ep. "
        podcast_like = sum(1 for ep in self.latest_episodes if isinstance(ep, DwEpisodeRecord) and "Ep. " in (ep.title or ""))
        ratio = podcast_like / total if total else 0
        if ratio >= 0.4:
            return ProbableShowType.podcast

        return ProbableShowType.series


    @computed_field(return_type=ProbableEpisodeIdentification)
    @property
    def probable_episode_identification(self) -> ProbableEpisodeIdentification:
        """
        Determine episode identification within this show.
        """
        # Numbered if this is a series
        if self.probable_show_type == ProbableShowType.series:
            return ProbableEpisodeIdentification.numbered

        # Unknown if fewer than 5 episodes
        total = len(self.latest_episodes or [])
        if total <= 5:
            return ProbableEpisodeIdentification.unknown

        # Numbered if >= 40% of episode titles contain the exact substring "Ep. "
        podcast_like = sum(1 for ep in self.latest_episodes if isinstance(ep, DwEpisodeRecord) and "Ep. " in (ep.title or ""))
        ratio = podcast_like / total if total else 0
        if ratio >= 0.4:
            return ProbableEpisodeIdentification.numbered

        return ProbableEpisodeIdentification.date_based


    @model_validator(mode="before")
    @classmethod
    def normalize_data(cls, data: Any):
        """
        If given a ShowPage payload, normalize to this model's shape.
        Otherwise (already normalized), return as-is.
        """
        if not isinstance(data, dict):
            return data

        normalized_data = {}
        if "show" in data and isinstance(data["show"], dict):
            normalized_data = data["show"]

        if "selectedSeason" in data and isinstance(data["selectedSeason"], dict):
            normalized_data["latest_season"] = data["selectedSeason"]

        # Find episodes in tabs and add to latest_episodes
        if "tabs" in data and isinstance(data["tabs"], list):
            for tab in data.get("tabs"):
                for comp in tab.get("components", []) or []:
                    items = comp.get("items", [])
                    first_type = items[0].get("type") if items[0] else None
                    if first_type != "ShowEpisode":
                        continue

                    for item in items:
                        normalized_data["latest_episodes"] = [item] + normalized_data.get("latest_episodes", [])

        return normalized_data

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DwShowRecord) and self.slug == other.slug

    def __hash__(self) -> int:
        return hash(self.slug)