from __future__ import annotations

from collections.abc import Mapping

from pydantic import AliasChoices, Field, field_validator, model_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.utils.custom_metadata import (
    CUSTOM_METADATA_KEY_MAX_LENGTH,
    CUSTOM_METADATA_MAX_ITEMS,
    CUSTOM_METADATA_VALUE_MAX_LENGTH,
    custom_metadata_from_items,
    is_valid_custom_metadata_key,
)


class CustomMetadataResponseBase(ResponseBase):
    """Response model base that derives custom metadata from generic metadata items."""

    custom_metadata: dict[str, str] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("custom_metadata", "meta_items"),
    )

    @field_validator("custom_metadata", mode="before")
    @classmethod
    def _read_custom_metadata(cls, value):
        if isinstance(value, Mapping):
            return dict(value)
        return custom_metadata_from_items(value)


class IndexingValueDefinitionAPI(RequestBase):
    key: str = Field(min_length=1, max_length=CUSTOM_METADATA_KEY_MAX_LENGTH)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("key")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        if not is_valid_custom_metadata_key(value):
            raise ValueError(
                "Indexing Value keys must use lowercase letters, numbers, and underscores, "
                "and start with a letter or underscore"
            )
        return value


class CustomMetadataAPIUpdate(RequestBase):
    """Replace one item's values and optionally remove shared fields for its media type."""

    custom_metadata: dict[str, str] = Field(default_factory=dict)
    removed_fields: list[str] = Field(default_factory=list)
    indexing_values: list[IndexingValueDefinitionAPI] | None = Field(default=None, max_length=100)

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
    def _validate_indexing_values(self):
        if self.indexing_values is None:
            return self
        keys = [value.key for value in self.indexing_values]
        if len(keys) != len(set(keys)):
            raise ValueError("Indexing Value keys must be unique")
        return self

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
