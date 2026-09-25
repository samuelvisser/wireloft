from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol

from backend.utils.custom_metadata import is_valid_custom_metadata_key


INDEX_DEFINITION_PREFIX = "custom_index.definition."
INDEX_ASSIGNMENT_PREFIX = "custom_index.assignment."


class _MetadataItem(Protocol):
    key: str
    value: str


class _MetadataResource(Protocol):
    meta_items: list[_MetadataItem]

    def set_meta(self, key: str, value: str | None) -> _MetadataItem:
        ...


@dataclass(frozen=True)
class IndexingValueDefinition:
    key: str
    name: str


class CustomIndexNotReadyError(RuntimeError):
    """Raised when an artifact needs a defined index that has not been assigned yet."""


def _validate_definition(key: str, name: str) -> IndexingValueDefinition:
    if not is_valid_custom_metadata_key(key):
        raise ValueError(
            "Indexing Value keys must use lowercase letters, numbers, and underscores, "
            "and must start with a letter or underscore"
        )
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Indexing Value names cannot be empty")
    if len(clean_name) > 120:
        raise ValueError("Indexing Value names cannot be longer than 120 characters")
    return IndexingValueDefinition(key=key, name=clean_name)


def index_definition_storage_key(key: str) -> str:
    if not is_valid_custom_metadata_key(key):
        raise ValueError(f"Invalid Indexing Value key: {key}")
    return f"{INDEX_DEFINITION_PREFIX}{key}"


def get_indexing_value_definitions(resource: _MetadataResource) -> list[IndexingValueDefinition]:
    definitions: list[IndexingValueDefinition] = []
    for item in resource.meta_items:
        if not item.key.startswith(INDEX_DEFINITION_PREFIX):
            continue
        key = item.key[len(INDEX_DEFINITION_PREFIX):]
        if not is_valid_custom_metadata_key(key):
            continue
        definitions.append(IndexingValueDefinition(key=key, name=item.value))
    return sorted(definitions, key=lambda item: item.key)


def indexing_value_definition_keys(resource: _MetadataResource) -> frozenset[str]:
    return frozenset(item.key for item in get_indexing_value_definitions(resource))


def replace_indexing_value_definitions(
    resource: _MetadataResource,
    definitions: Iterable[IndexingValueDefinition | Mapping[str, str]],
) -> None:
    normalized: list[IndexingValueDefinition] = []
    seen: set[str] = set()
    for definition in definitions:
        if isinstance(definition, IndexingValueDefinition):
            item = _validate_definition(definition.key, definition.name)
        elif isinstance(definition, Mapping):
            item = _validate_definition(str(definition["key"]), str(definition["name"]))
        else:
            item = _validate_definition(
                str(getattr(definition, "key")),
                str(getattr(definition, "name")),
            )
        if item.key in seen:
            raise ValueError(f"Duplicate Indexing Value key: {item.key}")
        seen.add(item.key)
        normalized.append(item)

    desired = {
        index_definition_storage_key(item.key): item.name
        for item in normalized
    }
    current = {
        item.key: item
        for item in resource.meta_items
        if item.key.startswith(INDEX_DEFINITION_PREFIX)
    }

    for storage_key, item in list(current.items()):
        if storage_key not in desired:
            resource.meta_items.remove(item)

    for storage_key, name in desired.items():
        existing = current.get(storage_key)
        if existing is None:
            resource.set_meta(storage_key, name)
        else:
            existing.value = name


def index_assignment_storage_key(key: str) -> str:
    if not is_valid_custom_metadata_key(key):
        raise ValueError(f"Invalid Indexing Value key: {key}")
    return f"{INDEX_ASSIGNMENT_PREFIX}{key}"


def get_media_download_index_assignments(download: _MetadataResource) -> dict[str, int]:
    assignments: dict[str, int] = {}
    for item in download.meta_items:
        if not item.key.startswith(INDEX_ASSIGNMENT_PREFIX):
            continue
        key = item.key[len(INDEX_ASSIGNMENT_PREFIX):]
        if not is_valid_custom_metadata_key(key):
            continue
        try:
            assignments[key] = int(item.value)
        except (TypeError, ValueError):
            continue
    return assignments


def set_media_download_index_assignment(
    download: _MetadataResource,
    key: str,
    value: int,
) -> None:
    if value < 1:
        raise ValueError("Custom index assignments must be positive integers")
    download.set_meta(index_assignment_storage_key(key), str(value))


def remove_media_download_index_assignments(
    download: _MetadataResource,
    *,
    keys: set[str] | frozenset[str] | None = None,
) -> None:
    exact = (
        {index_assignment_storage_key(key) for key in keys}
        if keys is not None
        else None
    )
    download.meta_items[:] = [
        item
        for item in download.meta_items
        if not (
            item.key.startswith(INDEX_ASSIGNMENT_PREFIX)
            and (exact is None or item.key in exact)
        )
    ]
