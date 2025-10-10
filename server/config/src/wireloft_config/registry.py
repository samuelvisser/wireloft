from __future__ import annotations

import threading
from typing import Optional

from .settings import AppSettings

# We avoid functools.lru_cache so we can explicitly control priming and reloading
_settings_lock = threading.RLock()
_SETTINGS: Optional[AppSettings] = None

def get_settings() -> AppSettings:
    """
    Return the process-wide AppSettings instance.
    The first call constructs it (reading YAML/.env/env, hashing admin pass, scrubbing WL_ADMIN_PASS).
    Subsequent calls return the cached instance.
    """
    global _SETTINGS
    if _SETTINGS is None:
        with _settings_lock:
            if _SETTINGS is None:  # double-checked locking
                _SETTINGS = AppSettings()
    return _SETTINGS

def reload_settings(*, overrides: dict | None = None) -> AppSettings:
    """
    Rebuild the settings instance (e.g., after changing config files).
    `overrides` are passed as kwargs (the highest precedence).
    """
    global _SETTINGS
    with _settings_lock:
        _SETTINGS = AppSettings(**(overrides or {}))
        return _SETTINGS
