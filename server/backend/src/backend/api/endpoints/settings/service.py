from __future__ import annotations

import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml

from backend.api.models.settings import SettingsAPIRead, SettingsAPIUpdate, SettingsValues
from config import get_settings, reload_settings
from config.settings.base import get_ui_config_path


logger = logging.getLogger(__name__)
_SETTINGS_FILE_LOCK = threading.Lock()

_UI_FILE_HEADER = """# Managed by the WireLoft Settings UI.
#
# Values in this file override config.yml, while environment variables remain
# the highest-priority deployment override. Edit through WireLoft when possible.
"""


class SettingsPersistenceError(RuntimeError):
    """Raised when the UI settings override file cannot be changed safely."""


def _file_timestamp(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _has_overrides(path: Path) -> bool:
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return False
    except OSError:
        # The GET endpoint should still return effective settings when metadata
        # about the source file is temporarily unavailable.
        return path.exists()


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
            # Permission changes are not supported on every mounted filesystem.
            pass

        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _serialize_override_document(values: SettingsValues) -> bytes:
    yaml_body = yaml.safe_dump(
        values.to_ui_override_document(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )
    return f"{_UI_FILE_HEADER}\n{yaml_body}".encode("utf-8")


def _reload_after_file_change() -> None:
    settings = reload_settings()

    # Most WireLoft code resolves settings lazily and therefore sees the new
    # instance immediately. Update the root log threshold too. Already-created
    # cron jobs are intentionally left alone until the next process restart;
    # interrupting running downloads just to rebuild the scheduler would be
    # more surprising than a clearly signposted restart requirement.
    logging.getLogger().setLevel(getattr(logging, settings.log_level, logging.INFO))


def _response() -> SettingsAPIRead:
    path = get_ui_config_path()
    return SettingsAPIRead(
        values=SettingsValues.from_app_settings(get_settings()),
        has_overrides=_has_overrides(path),
        updated_at=_file_timestamp(path),
    )


def get_ui_settings() -> SettingsAPIRead:
    return _response()


def save_ui_settings(body: SettingsAPIUpdate) -> SettingsAPIRead:
    with _SETTINGS_FILE_LOCK:
        path = get_ui_config_path()
        previous_content: bytes | None = None
        previous_file_existed = False

        try:
            previous_file_existed = path.exists()
            previous_content = path.read_bytes() if previous_file_existed else None
            _atomic_write(path, _serialize_override_document(body.values))
            _reload_after_file_change()
        except Exception as exc:
            logger.exception("Failed to persist Settings UI overrides")
            try:
                if previous_content is not None:
                    _atomic_write(path, previous_content)
                elif not previous_file_existed:
                    path.unlink(missing_ok=True)
                reload_settings()
            except Exception:
                logger.exception("Failed to restore the previous Settings UI override file")
            raise SettingsPersistenceError(
                "WireLoft could not save the settings override file. "
                "Check the permissions of the config directory."
            ) from exc

        return _response()


def reset_ui_settings() -> SettingsAPIRead:
    with _SETTINGS_FILE_LOCK:
        path = get_ui_config_path()
        previous_content: bytes | None = None

        try:
            previous_content = path.read_bytes() if path.exists() else None
            path.unlink(missing_ok=True)
            _reload_after_file_change()
        except Exception as exc:
            logger.exception("Failed to reset Settings UI overrides")
            try:
                if previous_content is not None:
                    _atomic_write(path, previous_content)
                reload_settings()
            except Exception:
                logger.exception("Failed to restore the Settings UI override file")
            raise SettingsPersistenceError(
                "WireLoft could not reset the settings override file. "
                "Check the permissions of the config directory."
            ) from exc

        return _response()
