from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from backend.api.models.base import RequestBase
from backend.utils.custom_metadata import (
    CUSTOM_METADATA_KEY_MAX_LENGTH,
    CUSTOM_METADATA_MAX_ITEMS,
    CUSTOM_METADATA_VALUE_MAX_LENGTH,
    is_valid_custom_metadata_key,
)


class CustomMetadataAPIUpdate(RequestBase):
    """Replace one item's values and optionally remove shared fields for its media type."""

    custom_metadata: dict[str, str] = Field(default_factory=dict)
    removed_fields: list[str] = Field(default_factory=list)

    @field_validator("custom_metadata")
    @classmethod
    def _validate_custom_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > CUSTOM_METADATA_MAX_ITEMS:
            raise ValueError(f"At most {CUSTOM_METADATA_MAX_ITEMS} custom metadata values are allowed")

        for key, item_value in value.items():
            cls._validate_key(key)
            if len(item_value) > CUSTOM_METADATA_VALUE_MAX_LENGTH:
                raise ValueError(
                    f"Metadata value '{key}' may be at most {CUSTOM_METADATA_VALUE_MAX_LENGTH} characters"
                )
        return value

    @field_validator("removed_fields")
    @classmethod
    def _validate_removed_fields(cls, value: list[str]) -> list[str]:
        if len(value) > CUSTOM_METADATA_MAX_ITEMS:
            raise ValueError(f"At most {CUSTOM_METADATA_MAX_ITEMS} metadata fields may be removed at once")
        if len(set(value)) != len(value):
            raise ValueError("Metadata fields to remove must be unique")
        for key in value:
            cls._validate_key(key)
        return value

    @model_validator(mode="after")
    def _validate_no_removed_field_is_readded(self):
        overlap = sorted(set(self.custom_metadata) & set(self.removed_fields))
        if overlap:
            raise ValueError(
                "A metadata field cannot be updated and removed in the same request: "
                + ", ".join(overlap)
            )
        return self

    @staticmethod
    def _validate_key(key: str) -> None:
        if not is_valid_custom_metadata_key(key):
            raise ValueError(
                "Metadata keys must use lowercase letters, numbers, and underscores, "
                f"start with a letter or underscore, and be at most {CUSTOM_METADATA_KEY_MAX_LENGTH} characters"
            )
