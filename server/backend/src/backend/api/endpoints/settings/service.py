from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic.alias_generators import to_snake
from pydantic_settings import DotEnvSettingsSource, EnvSettingsSource
from yaml.nodes import MappingNode, ScalarNode

from backend.api.models.settings import (
    SettingsAPIRead,
    SettingsAPIUpdate,
    SettingsValues,
    UI_SETTING_PATHS,
)
from config import get_settings, reload_settings
from config.settings.base import get_config_path, normalize_settings_source_keys
from config.settings.settings import AppSettings


logger = logging.getLogger(__name__)
_SETTINGS_FILE_LOCK = threading.Lock()
_MISSING = object()


class SettingsPersistenceError(RuntimeError):
    """Raised when config.yml cannot be changed safely."""


class SettingsManagedByEnvironmentError(RuntimeError):
    """Raised when a caller tries to change an environment-managed setting."""


def _file_timestamp(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _path_candidates(segment: str) -> tuple[str, ...]:
    snake = to_snake(segment)
    return (segment,) if snake == segment else (segment, snake)


def _get_document_value(document: dict[str, Any], path: str) -> Any:
    current: Any = document
    for segment in path.split("."):
        if not isinstance(current, dict):
            return _MISSING
        key = next((candidate for candidate in _path_candidates(segment) if candidate in current), None)
        if key is None:
            return _MISSING
        current = current[key]
    return current


def _load_config_document(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", {}
    except OSError as exc:
        raise SettingsPersistenceError(f"WireLoft could not read {path}.") from exc

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SettingsPersistenceError("config.yml contains invalid YAML.") from exc

    if loaded is None:
        return text, {}
    if not isinstance(loaded, dict):
        raise SettingsPersistenceError("config.yml must contain a YAML mapping at its root.")
    return text, loaded


def _configured_fields(document: dict[str, Any]) -> list[str]:
    return [
        path
        for path in UI_SETTING_PATHS
        if _get_document_value(document, path) is not _MISSING
    ]


def _environment_variable_name(path: str) -> str:
    return "WL_" + "__".join(to_snake(segment).upper() for segment in path.split("."))


def _source_document(source) -> dict[str, Any]:
    try:
        raw = source()
    except Exception:
        logger.exception("Failed to inspect a settings environment source")
        return {}
    return normalize_settings_source_keys(raw, AppSettings)


def _environment_overrides() -> dict[str, str]:
    """Return UI paths whose effective values are controlled above config.yml.

    Both process environment variables and WireLoft's configured .env file are
    included because neither can be overridden by editing config.yml.
    """
    source_documents = [
        _source_document(EnvSettingsSource(AppSettings)),
        _source_document(DotEnvSettingsSource(AppSettings)),
    ]

    managed: dict[str, str] = {}
    for path in UI_SETTING_PATHS:
        if not any(_get_document_value(document, path) is not _MISSING for document in source_documents):
            continue

        canonical_name = _environment_variable_name(path)
        parent_name = "WL_" + to_snake(path.split(".", 1)[0]).upper()
        actual_name = next(
            (
                name
                for name in os.environ
                if name.upper() in {canonical_name.upper(), parent_name.upper()}
            ),
            canonical_name,
        )
        managed[path] = actual_name
    return managed


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        try:
            os.chmod(temporary_path, 0o600)
        except (OSError, PermissionError, NotImplementedError):
            pass

        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _find_mapping_value(node: MappingNode, segment: str):
    candidates = set(_path_candidates(segment))
    for key_node, value_node in node.value:
        if isinstance(key_node, ScalarNode) and str(key_node.value) in candidates:
            return key_node, value_node
    return None


def _serialize_yaml_scalar(value: Any) -> str:
    """Serialize a UI value as a single YAML-safe scalar.

    JSON scalar syntax is valid YAML and avoids PyYAML's document terminator for
    scalar-only dumps while still correctly quoting paths, URLs and cron strings.
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _append_text(text: str, addition: str) -> str:
    if text and not text.endswith("\n"):
        text += "\n"
    return text + addition


def _insert_text(text: str, index: int, addition: str) -> str:
    prefix = "" if index == 0 or text[index - 1] == "\n" else "\n"
    return text[:index] + prefix + addition + text[index:]


def _patch_config_scalar(text: str, path: str, value: Any) -> str:
    """Add or update one scalar setting without rewriting unrelated YAML text.

    UI-exposed fields are at most one mapping below the root. Existing scalar
    values are replaced by parser mark offsets, preserving comments and the rest
    of config.yml byte-for-byte. Missing values are inserted only for the field
    the user actually changed.
    """
    serialized = _serialize_yaml_scalar(value)
    segments = path.split(".")
    if len(segments) not in {1, 2}:
        raise SettingsPersistenceError(f"Unsupported settings path: {path}")

    try:
        root = yaml.compose(text) if text.strip() else None
    except yaml.YAMLError as exc:
        raise SettingsPersistenceError("config.yml contains invalid YAML.") from exc

    if root is not None and not isinstance(root, MappingNode):
        raise SettingsPersistenceError("config.yml must contain a YAML mapping at its root.")

    if len(segments) == 1:
        if isinstance(root, MappingNode):
            existing = _find_mapping_value(root, segments[0])
            if existing is not None:
                _key_node, value_node = existing
                if not isinstance(value_node, ScalarNode):
                    raise SettingsPersistenceError(f"{path} must be a scalar setting in config.yml.")
                return text[:value_node.start_mark.index] + serialized + text[value_node.end_mark.index:]
        return _append_text(text, f"{segments[0]}: {serialized}\n")

    section_name, field_name = segments
    if isinstance(root, MappingNode):
        section_entry = _find_mapping_value(root, section_name)
        if section_entry is not None:
            _section_key, section_value = section_entry
            if isinstance(section_value, MappingNode):
                field_entry = _find_mapping_value(section_value, field_name)
                if field_entry is not None:
                    _field_key, field_value = field_entry
                    if not isinstance(field_value, ScalarNode):
                        raise SettingsPersistenceError(f"{path} must be a scalar setting in config.yml.")
                    return text[:field_value.start_mark.index] + serialized + text[field_value.end_mark.index:]

                return _insert_text(
                    text,
                    section_value.end_mark.index,
                    f"  {field_name}: {serialized}\n",
                )

            if isinstance(section_value, ScalarNode) and section_value.value in {"", "null", "~"}:
                return _insert_text(
                    text,
                    section_value.end_mark.index,
                    f"  {field_name}: {serialized}\n",
                )

            raise SettingsPersistenceError(f"{section_name} must be a mapping in config.yml.")

    return _append_text(text, f"{section_name}:\n  {field_name}: {serialized}\n")


def _value_for_path(values_document: dict[str, Any], path: str) -> Any:
    value = _get_document_value(values_document, path)
    if value is _MISSING:
        raise SettingsPersistenceError(f"Settings value missing for {path}.")
    return value


def _reload_after_file_change() -> None:
    settings = reload_settings()
    logging.getLogger().setLevel(getattr(logging, settings.log_level, logging.INFO))


def _response() -> SettingsAPIRead:
    path = get_config_path()
    _text, document = _load_config_document(path)
    return SettingsAPIRead(
        values=SettingsValues.from_app_settings(get_settings()),
        configured_fields=_configured_fields(document),
        environment_overrides=_environment_overrides(),
        updated_at=_file_timestamp(path),
    )


def get_ui_settings() -> SettingsAPIRead:
    return _response()


def save_ui_settings(body: SettingsAPIUpdate) -> SettingsAPIRead:
    with _SETTINGS_FILE_LOCK:
        path = get_config_path()
        previous_content: bytes | None = None
        previous_file_existed = False

        environment_overrides = _environment_overrides()
        blocked = [field for field in body.changed_fields if field in environment_overrides]
        if blocked:
            variables = ", ".join(environment_overrides[field] for field in blocked)
            raise SettingsManagedByEnvironmentError(
                f"These settings are managed by environment variables: {variables}."
            )

        try:
            previous_file_existed = path.exists()
            previous_content = path.read_bytes() if previous_file_existed else None
            text, _document = _load_config_document(path)
            values_document = body.values.to_config_document()

            # Only changedFields are touched. Merely opening or saving the page
            # therefore never expands config.yml with all application defaults.
            for field_path in body.changed_fields:
                text = _patch_config_scalar(
                    text,
                    field_path,
                    _value_for_path(values_document, field_path),
                )

            # Validate the complete YAML mapping before replacing the live file.
            parsed = yaml.safe_load(text) if text.strip() else {}
            if parsed is not None and not isinstance(parsed, dict):
                raise SettingsPersistenceError("config.yml must contain a YAML mapping at its root.")

            _atomic_write(path, text.encode("utf-8"))
            _reload_after_file_change()
        except SettingsManagedByEnvironmentError:
            raise
        except Exception as exc:
            logger.exception("Failed to persist settings to config.yml")
            try:
                if previous_content is not None:
                    _atomic_write(path, previous_content)
                elif not previous_file_existed:
                    path.unlink(missing_ok=True)
                reload_settings()
            except Exception:
                logger.exception("Failed to restore the previous config.yml")
            if isinstance(exc, SettingsPersistenceError):
                raise
            raise SettingsPersistenceError(
                "WireLoft could not save config.yml. Check the config file and directory permissions."
            ) from exc

        return _response()
