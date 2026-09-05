from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import Field, ValidationInfo, computed_field, field_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.utils.output_template import (
    MOVIE_OUTPUT_TEMPLATE_FIELDS,
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    movie_template_has_media_item_field,
    validate_output_template_fields,
)
from backend.utils.helpers import slugify


_MOVIE_EXTRA_COLLISION_MESSAGE = (
    "Movie and movie-extra downloads could resolve to the same file. Include at least "
    "one variable that describes the downloaded item, such as {{ title }}, {{ dw_id }}, "
    "{{ duration_seconds }}, or {{ media_type }}."
)


# ---------- Strict input (create/update) ----------
class _LocalMediaProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate hard here."""

    name: str = Field(min_length=1)
    type: LocalMediaProfileType
    preferred_format: PreferredFormat
    output_template: str = Field(min_length=16, max_length=4096)

    @computed_field(return_type=str)
    @property
    def slug(self) -> str:
        return slugify(self.name)

    @field_validator("output_template")
    @classmethod
    def _validate_output_template(cls, v: str, info: ValidationInfo) -> str:
        if not v.endswith(".ext"):
            raise ValueError("Output template must end with '.ext'")
        if not v.startswith("/downloads/"):
            raise ValueError("Output template must start with '/downloads/'")

        profile_type = info.data.get("type")
        if profile_type is None:
            return v

        allowed_fields = (
            MOVIE_OUTPUT_TEMPLATE_FIELDS
            if profile_type == LocalMediaProfileType.MOVIE
            else SHOW_OUTPUT_TEMPLATE_FIELDS
        )
        validate_output_template_fields(
            v,
            allowed_fields=allowed_fields,
        )

        if (
            profile_type == LocalMediaProfileType.MOVIE
            and not movie_template_has_media_item_field(v)
        ):
            raise ValueError(_MOVIE_EXTRA_COLLISION_MESSAGE)
        return v

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: LocalMediaProfileType) -> LocalMediaProfileType:
        if v == LocalMediaProfileType.BASE:
            raise ValueError("A Local Media Profile must be for shows or movies")
        return v

    @field_validator("preferred_format")
    @classmethod
    def _validate_preferred_format(
        cls,
        v: PreferredFormat,
        info: ValidationInfo,
    ) -> PreferredFormat:
        if (
            info.data.get("type") == LocalMediaProfileType.MOVIE
            and v == PreferredFormat.FORMAT_AUDIO_ONLY
        ):
            raise ValueError("Movie Local Media Profiles require a video format")
        return v


class _TypedLocalMediaProfileAPIBaseIn(_LocalMediaProfileAPIBaseIn):
    pass


class LocalMediaProfileAPICreate(_TypedLocalMediaProfileAPIBaseIn):
    """Request body for creating a media profile. Slug derived from name."""

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
    append_media_type_to_filename: bool


class LocalMediaProfileAPIRead(_LocalMediaProfileAPIBaseOut):
    """Response body for a media profile."""

    created_at: datetime
    updated_at: datetime


class LocalMediaProfileTemplateSource(ResponseBase):
    id: str
    label: str
    values: dict[str, str]
    fallback: bool = False


class LocalMediaProfileTemplateSources(ResponseBase):
    sources: list[LocalMediaProfileTemplateSource]


class LocalMediaProfileTemplatePreview(RequestBase):
    type: LocalMediaProfileType
    output_template: str = Field(min_length=1, max_length=4096)
    preferred_format: PreferredFormat
    values: dict[str, str] = Field(default_factory=dict)


class LocalMediaProfileTemplatePreviewResult(ResponseBase):
    output_path: str
    used_variables: list[str]
