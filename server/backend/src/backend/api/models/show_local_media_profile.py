from __future__ import annotations

from typing import Literal, Union

from pydantic import field_validator

from backend.api.models.local_media_profile import (
    LocalMediaProfileAPIBaseIn,
    LocalMediaProfileAPIBaseOut,
)
from backend.types.local_media_profile_types import (
    LocalMediaProfileType,
    ShowLocalMediaProfileScope,
)
from backend.utils.output_template import (
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    validate_output_template_path_requirements,
)


class _ShowLocalMediaProfileAPIBaseIn(LocalMediaProfileAPIBaseIn):
    type: Literal["show"] = LocalMediaProfileType.SHOW.value
    show_scope: ShowLocalMediaProfileScope = ShowLocalMediaProfileScope.BOTH

    @field_validator("output_template")
    @classmethod
    def _validate_output_template(cls, value: str) -> str:
        validate_output_template_path_requirements(
            value,
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
            allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
        )
        return value


class ShowLocalMediaProfileAPICreate(_ShowLocalMediaProfileAPIBaseIn):
    """Create a Show Local Media Profile."""


class ShowLocalMediaProfileAPIUpdate(_ShowLocalMediaProfileAPIBaseIn):
    """Update a Show Local Media Profile."""


class ShowLocalMediaProfileAPIRead(LocalMediaProfileAPIBaseOut):
    """Read a Show Local Media Profile."""

    type: Literal["show"] = LocalMediaProfileType.SHOW.value
    show_scope: Union[ShowLocalMediaProfileScope, str] = ShowLocalMediaProfileScope.BOTH
