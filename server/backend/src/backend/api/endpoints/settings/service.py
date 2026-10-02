from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic.alias_generators import to_camel, to_snake
from sqlalchemy import select
from yaml.nodes import MappingNode, ScalarNode

from backend.api.models.settings import (
    DownloadStorageInspectionValue,
    FilesystemInspectionValue,
    SettingFieldPath,
    SettingsAPIRead,
    SettingsAPIUpdate,
    SettingsValidationIssueValue,
    SettingsValues,
    UI_SETTING_PATHS,
)
from backend.db.models import Episode
from config import get_settings, replace_settings
from config.settings.base import (
    get_config_path,
    normalize_settings_source_keys,
)
from config.settings.cron_validation import (
    WorkerCronExpressionError,
    worker_cron_validation_errors,
)
from config.settings.settings import (
    AppSettings,
    TIMEZONE_ENVIRONMENT_VARIABLE,
    environment_settings_source_documents,
)
from dailywire_downloader.storage import inspect_filesystem
from task_manager.scheduler.operation_factory import create_operation
from task_manager.scheduler.operations import complete_operation, queue_operation_target_dispatch
from task_manager.tasks.helpers.episodes.same_episode import PENDING_EPISODE_STATUSES
from .operations import (
    FileWatcherCronOperation,
    FindEpisodesCronOperation,
    MonitorNoUsableMediaCronOperation,
    MonitorPendingEpisodesCronOperation,
    VerifyDownloadsCronOperation,
)


logger = logging.getLogger(__name__)
_SETTINGS_FILE_LOCK = threading.RLock()
_MISSING = object()


class SettingsPersistenceError(RuntimeError):
    """Raised when config.yml cannot be changed safely."""


class SettingsManagedByEnvironmentError(RuntimeError):
    """Raised when a caller tries to change an environment-managed setting."""


@dataclass(frozen=True)
class _SettingsRuntimeState:
    settings: AppSettings
    values: SettingsValues
    config_source: dict[str, Any]
    source_overrides: dict[str, Any]
    configured_fields: tuple[SettingFieldPath, ...]
    environment_overrides: dict[str, str]
    download_storage: DownloadStorageInspectionValue
    validation_issues: tuple[SettingsValidationIssueValue, ...]
    updated_at: datetime | None


class _SettingsRuntimeRegistry:
    """Thread-safe owner of the Settings UI runtime snapshot."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: _SettingsRuntimeState | None = None

    def get(self) -> _SettingsRuntimeState:
        with self._lock:
            settings = get_settings()
            if self._state is None or self._state.settings is not settings:
                self._state = _build_runtime_state(settings)
            return self._state

    def install(self, state: _SettingsRuntimeState) -> None:
        """Publish AppSettings and its UI snapshot as one runtime transition."""
        with self._lock:
            replace_settings(state.settings)
            self._state = state


_SETTINGS_RUNTIME = _SettingsRuntimeRegistry()


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


def _set_document_value(document: dict[str, Any], path: str, value: Any) -> None:
    segments = path.split(".")
    current = document
    for segment in segments[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    current[segments[-1]] = deepcopy(value)


def _read_config_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise SettingsPersistenceError(f"WireLoft could not read {path}.") from exc


def _load_config_document(path: Path) -> tuple[str, dict[str, Any]]:
    text = _read_config_text(path)
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SettingsPersistenceError("config.yml contains invalid YAML.") from exc

    if loaded is None:
        return text, {}
    if not isinstance(loaded, dict):
        raise SettingsPersistenceError("config.yml must contain a YAML mapping at its root.")
    return text, loaded


def _configured_fields(document: dict[str, Any]) -> tuple[SettingFieldPath, ...]:
    return tuple(
        cast(SettingFieldPath, path)
        for path in UI_SETTING_PATHS
        if _get_document_value(document, path) is not _MISSING
    )


def _environment_variable_name(path: str) -> str:
    if path == "timezone":
        return TIMEZONE_ENVIRONMENT_VARIABLE
    return "WL_" + "__".join(to_snake(segment).upper() for segment in path.split("."))


def _environment_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    """Snapshot environment settings once for the lifetime of the settings registry."""
    try:
        return environment_settings_source_documents(AppSettings)
    except Exception:
        logger.exception("Failed to inspect settings environment sources")
        return {}, {}


def _environment_overrides(
    environment_source: dict[str, Any],
    dotenv_source: dict[str, Any],
) -> dict[str, str]:
    """Return UI fields managed above config.yml in the startup source snapshot."""
    source_documents = (environment_source, dotenv_source)
    managed: dict[str, str] = {}

    for path in UI_SETTING_PATHS:
        if not any(_get_document_value(document, path) is not _MISSING for document in source_documents):
            continue

        canonical_name = _environment_variable_name(path)
        if path == "timezone":
            managed[path] = canonical_name
            continue

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


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _effective_source_shape(
    source: dict[str, Any],
    effective_document: dict[str, Any],
) -> dict[str, Any]:
    """Keep a source's shape while replacing raw values with validated values."""
    snapshot: dict[str, Any] = {}
    for key, raw_value in source.items():
        effective_value = effective_document.get(key, _MISSING)
        if effective_value is _MISSING:
            continue
        if isinstance(raw_value, dict) and isinstance(effective_value, dict):
            nested = _effective_source_shape(raw_value, effective_value)
            if nested:
                snapshot[key] = nested
            continue
        snapshot[key] = deepcopy(effective_value)
    return snapshot


def _source_overrides_snapshot(
    settings: AppSettings,
    environment_source: dict[str, Any],
    dotenv_source: dict[str, Any],
) -> dict[str, Any]:
    """Snapshot source precedence without retaining raw environment secrets."""
    effective_document = settings.model_dump(mode="python", by_alias=True)
    dotenv_snapshot = _effective_source_shape(dotenv_source, effective_document)
    environment_snapshot = _effective_source_shape(environment_source, effective_document)
    return _deep_merge(dotenv_snapshot, environment_snapshot)


def _effective_settings_from_sources(
    state: _SettingsRuntimeState,
    config_source: dict[str, Any],
) -> AppSettings:
    """Build settings from already-loaded sources without touching config/.env again."""
    merged = _deep_merge(config_source, state.source_overrides)

    # These values are process-owned rather than useful file sources. Reuse the
    # startup values so UI saves never reread pyproject.toml or re-hash a
    # plaintext admin password that the startup loader already scrubbed.
    merged["appVersion"] = state.settings.app_version
    merged["adminAuth"] = state.settings.admin_auth.model_dump(
        mode="python",
        by_alias=True,
    )
    return AppSettings.model_validate(merged)


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
    """Serialize a UI value as a single YAML-safe scalar."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _append_text(text: str, addition: str) -> str:
    if text and not text.endswith("\n"):
        text += "\n"
    return text + addition


@dataclass(frozen=True)
class _TextEdit:
    start: int
    end: int
    replacement: str


def _patch_config_scalars(text: str, changes: dict[str, Any]) -> str:
    """Apply all UI scalar changes after parsing the YAML syntax tree once."""
    try:
        root = yaml.compose(text) if text.strip() else None
    except yaml.YAMLError as exc:
        raise SettingsPersistenceError("config.yml contains invalid YAML.") from exc

    if root is not None and not isinstance(root, MappingNode):
        raise SettingsPersistenceError("config.yml must contain a YAML mapping at its root.")

    edits: list[_TextEdit] = []
    section_insertions: dict[int, list[str]] = {}
    root_additions: list[str] = []
    missing_sections: dict[str, list[str]] = {}

    for path, value in changes.items():
        serialized = _serialize_yaml_scalar(value)
        segments = path.split(".")
        if len(segments) not in {1, 2}:
            raise SettingsPersistenceError(f"Unsupported settings path: {path}")

        if len(segments) == 1:
            existing = _find_mapping_value(root, segments[0]) if isinstance(root, MappingNode) else None
            if existing is None:
                root_additions.append(f"{segments[0]}: {serialized}\n")
                continue

            _key_node, value_node = existing
            if not isinstance(value_node, ScalarNode):
                raise SettingsPersistenceError(f"{path} must be a scalar setting in config.yml.")
            edits.append(_TextEdit(value_node.start_mark.index, value_node.end_mark.index, serialized))
            continue

        section_name, field_name = segments
        section_entry = _find_mapping_value(root, section_name) if isinstance(root, MappingNode) else None
        if section_entry is None:
            missing_sections.setdefault(section_name, []).append(
                f"  {field_name}: {serialized}\n"
            )
            continue

        _section_key, section_value = section_entry
        if isinstance(section_value, ScalarNode) and section_value.value in {"", "null", "~"}:
            section_insertions.setdefault(section_value.end_mark.index, []).append(
                f"  {field_name}: {serialized}\n"
            )
            continue
        if not isinstance(section_value, MappingNode):
            raise SettingsPersistenceError(f"{section_name} must be a mapping in config.yml.")
        if section_value.flow_style:
            raise SettingsPersistenceError(
                f"{section_name} must use a block mapping in config.yml before it can be edited in Settings."
            )

        field_entry = _find_mapping_value(section_value, field_name)
        if field_entry is not None:
            _field_key, field_value = field_entry
            if not isinstance(field_value, ScalarNode):
                raise SettingsPersistenceError(f"{path} must be a scalar setting in config.yml.")
            edits.append(_TextEdit(field_value.start_mark.index, field_value.end_mark.index, serialized))
            continue

        section_insertions.setdefault(section_value.end_mark.index, []).append(
            f"  {field_name}: {serialized}\n"
        )

    for index, additions in section_insertions.items():
        prefix = "" if index == 0 or text[index - 1] == "\n" else "\n"
        edits.append(_TextEdit(index, index, prefix + "".join(additions)))

    for edit in sorted(edits, key=lambda item: (item.start, item.end), reverse=True):
        text = text[:edit.start] + edit.replacement + text[edit.end:]

    additions = list(root_additions)
    for section_name, section_values in missing_sections.items():
        additions.append(f"{section_name}:\n{''.join(section_values)}")
    if additions:
        text = _append_text(text, "".join(additions))

    return text


def _value_for_path(values_document: dict[str, Any], path: str) -> Any:
    value = _get_document_value(values_document, path)
    if value is _MISSING:
        raise SettingsPersistenceError(f"Settings value missing for {path}.")
    return value


def _same_inspected_filesystem(first, second) -> bool | None:
    try:
        return first.existing_path.stat().st_dev == second.existing_path.stat().st_dev
    except OSError:
        return None


def _download_storage(settings: AppSettings) -> DownloadStorageInspectionValue:
    download_settings = settings.download_settings
    download_root = inspect_filesystem(download_settings.download_root)
    temporary_root = inspect_filesystem(download_settings.temporary_download_root)

    return DownloadStorageInspectionValue(
        download_root=FilesystemInspectionValue(
            path=str(download_root.path),
            mount_point=str(download_root.mount_point) if download_root.mount_point is not None else None,
            filesystem_type=download_root.filesystem_type,
            storage_kind=download_root.storage_kind,
        ),
        temporary_download_root=FilesystemInspectionValue(
            path=str(temporary_root.path),
            mount_point=str(temporary_root.mount_point) if temporary_root.mount_point is not None else None,
            filesystem_type=temporary_root.filesystem_type,
            storage_kind=temporary_root.storage_kind,
        ),
        same_filesystem=_same_inspected_filesystem(download_root, temporary_root),
    )


def _validation_issues(
    settings: AppSettings,
    *,
    configured_fields: tuple[SettingFieldPath, ...],
    environment_overrides: dict[str, str],
) -> tuple[SettingsValidationIssueValue, ...]:
    issues: list[SettingsValidationIssueValue] = []
    configured = set(configured_fields)

    for error in worker_cron_validation_errors(settings):
        field = cast(
            SettingFieldPath,
            ".".join(to_camel(segment) for segment in error.field_path),
        )
        source = environment_overrides.get(field)
        if source is None:
            source = "config.yml" if field in configured else "built-in default"

        code = (
            "cron_expression_invalid"
            if isinstance(error, WorkerCronExpressionError)
            else "worker_cron_interval_too_short"
        )
        issues.append(SettingsValidationIssueValue(
            field=field,
            code=code,
            message=str(error),
            source=source,
        ))

    return tuple(issues)


def _build_runtime_state(settings: AppSettings) -> _SettingsRuntimeState:
    path = get_config_path()
    _text, document = _load_config_document(path)
    raw_config_source = normalize_settings_source_keys(document, AppSettings)
    effective_document = settings.model_dump(mode="python", by_alias=True)
    config_source = _effective_source_shape(raw_config_source, effective_document)
    environment_source, dotenv_source = _environment_sources()
    configured_fields = _configured_fields(document)
    environment_overrides = _environment_overrides(environment_source, dotenv_source)
    source_overrides = _source_overrides_snapshot(
        settings,
        environment_source,
        dotenv_source,
    )
    validation_issues = _validation_issues(
        settings,
        configured_fields=configured_fields,
        environment_overrides=environment_overrides,
    )

    for issue in validation_issues:
        logger.error(
            "Settings validation issue in %s for %s: %s",
            issue.source,
            issue.field,
            issue.message,
        )

    return _SettingsRuntimeState(
        settings=settings,
        values=SettingsValues.from_app_settings(settings),
        config_source=config_source,
        source_overrides=source_overrides,
        configured_fields=configured_fields,
        environment_overrides=environment_overrides,
        download_storage=_download_storage(settings),
        validation_issues=validation_issues,
        updated_at=_file_timestamp(path),
    )


def initialize_settings_runtime_state() -> None:
    """Prime Settings UI metadata and diagnostics once during application startup."""
    _SETTINGS_RUNTIME.get()


def _runtime_state() -> _SettingsRuntimeState:
    return _SETTINGS_RUNTIME.get()


def _response(state: _SettingsRuntimeState) -> SettingsAPIRead:
    return SettingsAPIRead(
        values=state.values,
        configured_fields=list(state.configured_fields),
        environment_overrides=dict(state.environment_overrides),
        download_storage=state.download_storage,
        validation_issues=list(state.validation_issues),
        updated_at=state.updated_at,
    )


def get_ui_settings() -> SettingsAPIRead:
    """Return the startup/saved settings snapshot without rereading file sources."""
    return _response(_runtime_state())


def save_ui_settings(body: SettingsAPIUpdate) -> SettingsAPIRead:
    with _SETTINGS_FILE_LOCK:
        state = _runtime_state()
        path = get_config_path()
        blocked = [field for field in body.changed_fields if field in state.environment_overrides]
        if blocked:
            variables = ", ".join(state.environment_overrides[field] for field in blocked)
            raise SettingsManagedByEnvironmentError(
                f"These settings are managed by environment variables: {variables}."
            )

        previous_content: bytes | None
        try:
            previous_content = path.read_bytes()
            text = previous_content.decode("utf-8")
            previous_file_existed = True
        except FileNotFoundError:
            previous_content = None
            text = ""
            previous_file_existed = False
        except (OSError, UnicodeDecodeError) as exc:
            raise SettingsPersistenceError(f"WireLoft could not read {path}.") from exc

        values_document = body.values.to_config_document()
        changes = {
            field: _value_for_path(values_document, field)
            for field in body.changed_fields
        }

        try:
            patched_text = _patch_config_scalars(text, changes)

            config_source = deepcopy(state.config_source)
            for field, value in changes.items():
                _set_document_value(config_source, field, value)

            effective_settings = _effective_settings_from_sources(state, config_source)
            config_source = _effective_source_shape(
                config_source,
                effective_settings.model_dump(mode="python", by_alias=True),
            )
            configured_fields = tuple(dict.fromkeys((*state.configured_fields, *body.changed_fields)))
            validation_issues = _validation_issues(
                effective_settings,
                configured_fields=configured_fields,
                environment_overrides=state.environment_overrides,
            )

            storage_fields = {
                "downloadSettings.downloadRoot",
                "downloadSettings.temporaryDownloadRoot",
            }
            download_storage = (
                _download_storage(effective_settings)
                if storage_fields.intersection(body.changed_fields)
                else state.download_storage
            )

            _atomic_write(path, patched_text.encode("utf-8"))
            next_state = _SettingsRuntimeState(
                settings=effective_settings,
                values=SettingsValues.from_app_settings(effective_settings),
                config_source=config_source,
                source_overrides=state.source_overrides,
                configured_fields=configured_fields,
                environment_overrides=state.environment_overrides,
                download_storage=download_storage,
                validation_issues=validation_issues,
                updated_at=_file_timestamp(path),
            )
            _SETTINGS_RUNTIME.install(next_state)

            logging.getLogger().setLevel(
                getattr(logging, effective_settings.log_level, logging.INFO)
            )
            return _response(next_state)
        except SettingsManagedByEnvironmentError:
            raise
        except Exception as exc:
            logger.exception("Failed to persist settings to config.yml")
            try:
                if previous_content is not None:
                    _atomic_write(path, previous_content)
                elif not previous_file_existed:
                    path.unlink(missing_ok=True)
                _SETTINGS_RUNTIME.install(state)
            except Exception:
                logger.exception("Failed to restore the previous config.yml")

            if isinstance(exc, SettingsPersistenceError):
                raise
            raise SettingsPersistenceError(
                "WireLoft could not save config.yml. Check the config file and directory permissions."
            ) from exc


_CRON_OPERATION_FACTORIES = {
    "find-episodes": FindEpisodesCronOperation,
    "monitor-no-usable-media": MonitorNoUsableMediaCronOperation,
    "verify-downloads": VerifyDownloadsCronOperation,
    "file-watcher": FileWatcherCronOperation,
}


def run_cron_job_now(session, job: str) -> dict[str, bool | str]:
    """Run one Settings cron job immediately as a durable UI TaskOperation."""
    if job == "monitor-pending-episodes":
        episode_ids = tuple(
            session.scalars(
                select(Episode.id).where(Episode.publish_status.in_(PENDING_EPISODE_STATUSES))
            )
        )
        operation = create_operation(
            session,
            MonitorPendingEpisodesCronOperation(episode_ids),
        )
        if not episode_ids:
            complete_operation(
                session,
                operation.id,
                summary="No pending episodes to monitor",
                data={"episodes_requested": 0},
            )
            return {"queued": False, "operation_id": operation.id}
    else:
        factory = _CRON_OPERATION_FACTORIES.get(job)
        if factory is None:
            raise ValueError(f"Unknown cron job: {job}")
        operation = create_operation(session, factory())

    for target in operation.targets:
        queue_operation_target_dispatch(session, operation.id, target.slot_key)

    return {"queued": True, "operation_id": operation.id}
