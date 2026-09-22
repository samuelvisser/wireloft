from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from backend.api.models.local_media_profile import (
    LocalMediaProfileAPIBaseIn,
    LocalMediaProfileAPIBaseOut,
)
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.utils.output_template import (
    MOVIE_OUTPUT_TEMPLATE_FIELDS,
    MOVIE_OUTPUT_TEMPLATE_METADATA_SCOPES,
    movie_template_has_media_item_field,
    validate_output_template_path_requirements,
)


_MOVIE_EXTRA_COLLISION_MESSAGE = (
    "Movie and movie-extra downloads could resolve to the same file. Include at least "
    "one variable that describes the downloaded item, such as {{ title }}, {{ slug }}, "
    "{{ duration_seconds }}, or {{ media_type }}."
)

class _MovieLocalMediaProfileAPIBaseIn(LocalMediaProfileAPIBaseIn):
    type: Literal["movie"] = LocalMediaProfileType.MOVIE.value

    @field_validator("preferred_format")
    @classmethod
    def _require_video_format(cls, value: PreferredFormat) -> PreferredFormat:
        if value == PreferredFormat.FORMAT_AUDIO_ONLY:
            raise ValueError("Movie Local Media Profiles require a video format")
        return value

    @field_validator("output_template")
    @classmethod
    def _validate_output_template(cls, value: str) -> str:
        validate_output_template_path_requirements(
            value,
            allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS,
            allowed_metadata_scopes=MOVIE_OUTPUT_TEMPLATE_METADATA_SCOPES,
        )
        if not movie_template_has_media_item_field(value):
            raise ValueError(_MOVIE_EXTRA_COLLISION_MESSAGE)
        return value


class MovieLocalMediaProfileAPICreate(_MovieLocalMediaProfileAPIBaseIn):
    """Create a Movie Local Media Profile."""


class MovieLocalMediaProfileAPIUpdate(_MovieLocalMediaProfileAPIBaseIn):
    """Update a Movie Local Media Profile."""


class MovieLocalMediaProfileAPIRead(LocalMediaProfileAPIBaseOut):
    """Read a Movie Local Media Profile."""

    type: Literal["movie"] = LocalMediaProfileType.MOVIE.value
