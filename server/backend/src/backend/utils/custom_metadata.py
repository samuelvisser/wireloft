from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Literal, Protocol


class _MetadataItem(Protocol):
    key: str
    value: str


class _CustomMetadataResource(Protocol):
    meta_items: list[_MetadataItem]

    def set_meta(self, key: str, value: str | None) -> _MetadataItem:
        ...


CustomMetadataScope = Literal["show", "movie"]

CUSTOM_METADATA_DB_PREFIX = "custom."
CUSTOM_METADATA_KEY_MAX_LENGTH = 64
CUSTOM_METADATA_VALUE_MAX_LENGTH = 4096
CUSTOM_METADATA_MAX_ITEMS = 100
CUSTOM_METADATA_KEY_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")

CUSTOM_METADATA_TEMPLATE_PREFIXES: dict[CustomMetadataScope, str] = {
    "show": "meta_show_",
    "movie": "meta_movie_",
}


def is_valid_custom_metadata_key(key: str) -> bool:
    return (
        0 < len(key) <= CUSTOM_METADATA_KEY_MAX_LENGTH
        and CUSTOM_METADATA_KEY_PATTERN.fullmatch(key) is not None
    )


def custom_metadata_storage_key(key: str) -> str:
    if not is_valid_custom_metadata_key(key):
        raise ValueError(
            "Metadata keys must use lowercase letters, numbers, and underscores, "
            "and must start with a letter or underscore"
        )
    return f"{CUSTOM_METADATA_DB_PREFIX}{key}"


def custom_metadata_from_items(items: Iterable[_MetadataItem]) -> dict[str, str]:
    """Extract user-editable values from generic metadata items."""
    result: dict[str, str] = {}
    for item in items:
        if not item.key.startswith(CUSTOM_METADATA_DB_PREFIX):
            continue
        key = item.key[len(CUSTOM_METADATA_DB_PREFIX):]
        if is_valid_custom_metadata_key(key):
            result[key] = item.value
    return result


def get_custom_metadata(resource: _CustomMetadataResource) -> dict[str, str]:
    """Return only user-editable metadata, isolated from WireLoft internal keys."""
    return custom_metadata_from_items(resource.meta_items)


def replace_custom_metadata(
    resource: _CustomMetadataResource,
    values: Mapping[str, str],
) -> None:
    """Replace an item's custom values without touching WireLoft metadata."""
    storage_values = {
        custom_metadata_storage_key(key): value
        for key, value in values.items()
    }
    current = {
        item.key: item
        for item in resource.meta_items
        if item.key.startswith(CUSTOM_METADATA_DB_PREFIX)
    }

    for storage_key, item in list(current.items()):
        if storage_key not in storage_values:
            resource.meta_items.remove(item)

    for storage_key, value in storage_values.items():
        item = current.get(storage_key)
        if item is None:
            resource.set_meta(storage_key, value)
        else:
            item.value = value


def custom_metadata_template_variable(scope: CustomMetadataScope, key: str) -> str:
    if not is_valid_custom_metadata_key(key):
        raise ValueError(f"Invalid custom metadata key: {key}")
    return f"{CUSTOM_METADATA_TEMPLATE_PREFIXES[scope]}{key}"


def parse_custom_metadata_template_variable(
    variable: str,
) -> tuple[CustomMetadataScope, str] | None:
    for scope, prefix in CUSTOM_METADATA_TEMPLATE_PREFIXES.items():
        if not variable.startswith(prefix):
            continue
        key = variable[len(prefix):]
        if is_valid_custom_metadata_key(key):
            return scope, key
    return None


def is_allowed_custom_metadata_template_variable(
    variable: str,
    *,
    scopes: frozenset[CustomMetadataScope],
) -> bool:
    parsed = parse_custom_metadata_template_variable(variable)
    return parsed is not None and parsed[0] in scopes


def custom_metadata_template_values(
    scope: CustomMetadataScope,
    metadata: Mapping[str, str] | None,
) -> dict[str, str]:
    if not metadata:
        return {}
    return {
        custom_metadata_template_variable(scope, key): value
        for key, value in metadata.items()
        if is_valid_custom_metadata_key(key)
    }
