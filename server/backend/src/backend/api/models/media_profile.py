from __future__ import annotations

from datetime import datetime

from pydantic import computed_field, Field, field_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.media_profile_types import PreferredFormat
from backend.utils.helpers import slugify


def validate_output_template(v: str) -> str:
    """Validates the output template."""
    if not v.endswith(".ext"):
        raise ValueError("Output template must end with '.ext'")

    if not v.startswith("/downloads/"):
        raise ValueError("Output template must start with '/downloads/'")
    return v


class _MediaProfileAPIBase:
    """Fields common to all media profile models."""

    name: str = Field(min_length=1)
    output_template: str
    preferred_format: PreferredFormat
    download_series_images: bool


class MediaProfileAPICreate(_MediaProfileAPIBase, RequestBase):
    """Request body for creating a media profile.
    Slug is generated automatically from the provided name.
    """

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return slugify(self.name)

    @field_validator("output_template")
    @classmethod
    def validate_output_template(cls, v: str) -> str:
        return validate_output_template(v)



class MediaProfileAPIRead(_MediaProfileAPIBase, ResponseBase):
    """Response body for a media profile."""
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime


class MediaProfileAPIUpdate(_MediaProfileAPIBase, RequestBase):
    """Request body for updating a media profile."""

    @field_validator("output_template")
    @classmethod
    def validate_output_template(cls, v: str) -> str:
        return validate_output_template(v)

    # @computed_field(return_type=str)
    # @property
    # def slug(self) -> str:
    #     return slugify(self.name)