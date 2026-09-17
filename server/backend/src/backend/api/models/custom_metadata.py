from __future__ import annotations

from pydantic import Field, field_validator

from backend.api.models.base import RequestBase
from backend.utils.custom_metadata import (
    CUSTOM_METADATA_KEY_MAX_LENGTH,
    CUSTOM_METADATA_MAX_ITEMS,
    CUSTOM_METADATA_VALUE_MAX_LENGTH,
    is_valid_custom_metadata_key,
)


class CustomMetadataAPIUpdate(RequestBase):
    """Replace the user-defined custom metadata attached to one resource."""

    custom_metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("custom_metadata")
    @classmethod
    def _validate_custom_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > CUSTOM_METADATA_MAX_ITEMS:
            raise ValueError(f"At most {CUSTOM_METADATA_MAX_ITEMS} custom metadata values are allowed")

        for key, item_value in value.items():
            if not is_valid_custom_metadata_key(key):
                raise ValueError(
                    "Metadata keys must use lowercase letters, numbers, and underscores, "
                    f"start with a letter or underscore, and be at most {CUSTOM_METADATA_KEY_MAX_LENGTH} characters"
                )
            if len(item_value) > CUSTOM_METADATA_VALUE_MAX_LENGTH:
                raise ValueError(
                    f"Metadata value '{key}' may be at most {CUSTOM_METADATA_VALUE_MAX_LENGTH} characters"
                )
        return value
