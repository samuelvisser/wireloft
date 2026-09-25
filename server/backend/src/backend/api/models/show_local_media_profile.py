from __future__ import annotations

from typing import Literal, Union

from pydantic import Field, field_validator, model_validator

from backend.api.models.local_media_profile import (
    LocalMediaProfileAPIBaseIn,
    LocalMediaProfileAPIBaseOut,
)
from backend.api.models.custom_metadata import IndexingValueDefinitionAPI
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
    indexing_values: list[IndexingValueDefinitionAPI] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _unique_index_keys(self):
        keys = [item.key for item in self.indexing_values]
        if len(keys) != len(set(keys)):
            raise ValueError("Indexing Value keys must be unique")
        return self

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
    indexing_values: list[IndexingValueDefinitionAPI] = Field(default_factory=list)
