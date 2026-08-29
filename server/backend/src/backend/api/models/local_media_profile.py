from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import computed_field, Field, field_validator, model_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.utils.output_template import (
    MOVIE_OUTPUT_TEMPLATE_FIELDS,
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    validate_output_template_fields,
)
from backend.utils.helpers import slugify


# ---------- Strict input (create/update) ----------
class _LocalMediaProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate hard here."""

    name: str = Field(min_length=1)
    output_template: str = Field(min_length=16)
    preferred_format: PreferredFormat

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


class _TypedLocalMediaProfileAPIBaseIn(_LocalMediaProfileAPIBaseIn):
    type: LocalMediaProfileType

    @model_validator(mode="after")
    def _validate_type_specific_fields(self):
        if self.type == LocalMediaProfileType.BASE:
            raise ValueError("A Local Media Profile must be for shows or movies")

        allowed_fields = (
            MOVIE_OUTPUT_TEMPLATE_FIELDS
            if self.type == LocalMediaProfileType.MOVIE
            else SHOW_OUTPUT_TEMPLATE_FIELDS
        )
        validate_output_template_fields(
            self.output_template,
            allowed_fields=allowed_fields,
        )

        if (
            self.type == LocalMediaProfileType.MOVIE
            and self.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY
        ):
            raise ValueError("Movie Local Media Profiles require a video format")
        return self


class LocalMediaProfileAPICreate(_TypedLocalMediaProfileAPIBaseIn):
    """Request body for creating a media profile. Slug derived from name."""

    # Existing clients created show profiles before this discriminator existed.
    type: LocalMediaProfileType = LocalMediaProfileType.SHOW


class LocalMediaProfileAPIUpdate(_TypedLocalMediaProfileAPIBaseIn):
    """Request body for updating a media profile."""
    pass


# ---------- Lenient output (read) ----------
class _LocalMediaProfileAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    type: Union[LocalMediaProfileType, str]
    slug: str
    name: str
    output_template: str
    preferred_format: Union[PreferredFormat, str]


class LocalMediaProfileAPIRead(_LocalMediaProfileAPIBaseOut):
    """Response body for a media profile."""

    created_at: datetime
    updated_at: datetime
