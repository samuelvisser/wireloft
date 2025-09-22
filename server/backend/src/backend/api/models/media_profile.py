from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import computed_field, Field, field_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.media_profile_types import PreferredFormat
from backend.utils.helpers import slugify


# ---------- Strict input (create/update) ----------
class _MediaProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate hard here."""

    name: str = Field(min_length=1)
    output_template: str = Field(min_length=16)
    preferred_format: PreferredFormat
    download_series_images: bool

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return slugify(self.name)

    @field_validator("output_template")
    @classmethod
    def _validate_output_template(cls, v: str) -> str:
        if not v.endswith(".ext"):
            raise ValueError("Output template must end with '.ext'")
        if not v.startswith("/downloads/"):
            raise ValueError("Output template must start with '/downloads/'")
        return v


class MediaProfileAPICreate(_MediaProfileAPIBaseIn):
    """Request body for creating a media profile. Slug derived from name."""
    pass


class MediaProfileAPIUpdate(_MediaProfileAPIBaseIn):
    """Request body for updating a media profile."""
    pass


# ---------- Lenient output (read) ----------
class _MediaProfileAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    slug: str
    name: str
    output_template: str
    preferred_format: Union[PreferredFormat, str]
    download_series_images: bool


class MediaProfileAPIRead(_MediaProfileAPIBaseOut):
    """Response body for a media profile."""

    created_at: datetime
    updated_at: datetime