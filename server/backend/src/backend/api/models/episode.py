from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional, Union
from datetime import datetime

from pydantic import AwareDatetime, computed_field, model_validator

from backend.api.models.base import ResponseBase, RequestBase
from backend.types.episode_types import EpisodePublishStatus
from backend.utils.episode import EpisodeIdentifierInfo

from backend.utils.helpers import generate_uuid


# ---------- Strict input (create/update) ----------
class _EpisodeAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""
    # Episode lifecycle/context fields
    publish_status: EpisodePublishStatus
    went_live_date: Optional[AwareDatetime]
    published_date: Optional[AwareDatetime]

    # Reusable content metadata
    title: str
    description: str


class EpisodeAPICreate(_EpisodeAPIBaseIn):
    """Request body for creating an episode."""

    show_id: int
    index: int
    slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class EpisodeAPIUpdate(_EpisodeAPIBaseIn):
    """Request body for updating an episode."""
    pass

# ---------- Lenient output (read) ----------
class _EpisodeIdentifierAPIOut(ResponseBase):
    """Shared canonical episode-identifier fields for API response models."""

    episode_identifier: str
    dw_episode_number: Optional[str]
    episode_type: Optional[str]
    episode_extra_type: Optional[str]
    episode_number: Optional[str]
    episode_sub_number: Optional[str]
    episode_label: str

    @model_validator(mode="before")
    @classmethod
    def derive_identifier_fields(cls, value: Any) -> Any:
        """Expand compact SQLAlchemy row mappings from the canonical identifier."""
        if not isinstance(value, Mapping):
            return value

        identifier = value.get("episode_identifier")
        if not isinstance(identifier, str):
            return value

        identifier_info = EpisodeIdentifierInfo.from_identifier(identifier)
        values = dict(value)
        values.update(
            episode_type=identifier_info.type,
            episode_extra_type=identifier_info.extra_type,
            episode_number=identifier_info.episode_number,
            episode_sub_number=identifier_info.sub_episode_number,
            episode_label=identifier_info.label,
        )
        return values


class _EpisodeAPIBaseOut(_EpisodeIdentifierAPIOut):
    """Complete episode response fields shared by full read models."""

    id: int
    show_id: int
    season_id: int
    index: int
    publish_status: Union[EpisodePublishStatus, str]
    went_live_date: Optional[datetime]
    published_date: Optional[datetime]
    scheduled_date: Optional[datetime]
    sharing_url: str
    early_delete_available: bool = False

    title: str
    description: str
    duration: float
    uuid: str
    slug: str
    background_image_path: Optional[str]
    thumbnail_landscape_path: Optional[str]
    thumbnail_portrait_path: Optional[str]
    thumbnail_square_path: Optional[str]


class EpisodeAPIRead(_EpisodeAPIBaseOut):
    """Represents a complete episode returned by the detail/full-list API."""

    created_at: datetime
    updated_at: datetime


class EpisodeAPIReadView(_EpisodeIdentifierAPIOut):
    """Small episode representation used by show grids and browser-side warm caches."""

    id: int
    show_id: int
    season_id: int
    index: int
    publish_status: Union[EpisodePublishStatus, str]
    title: str
    slug: str
    thumbnail_landscape_path: Optional[str]
