from fastapi import APIRouter, HTTPException

from backend.api.models.settings import SettingsAPIRead, SettingsAPIUpdate
from .service import (
    SettingsPersistenceError,
    get_ui_settings,
    reset_ui_settings,
    save_ui_settings,
)


router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=SettingsAPIRead)
def settings_get():
    """Return all settings intentionally exposed by the WireLoft UI."""
    return get_ui_settings()


@router.put("", response_model=SettingsAPIRead)
def settings_update(body: SettingsAPIUpdate):
    """Replace the Settings UI override document with validated values."""
    try:
        return save_ui_settings(body)
    except SettingsPersistenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("", response_model=SettingsAPIRead)
def settings_reset():
    """Remove every UI override and fall back to config.yml/default values."""
    try:
        return reset_ui_settings()
    except SettingsPersistenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
