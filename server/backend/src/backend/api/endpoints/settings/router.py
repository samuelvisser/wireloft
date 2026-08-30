from fastapi import APIRouter, HTTPException

from backend.api.models.settings import SettingsAPIRead, SettingsAPIUpdate
from .service import (
    SettingsManagedByEnvironmentError,
    SettingsPersistenceError,
    get_ui_settings,
    save_ui_settings,
)


router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=SettingsAPIRead)
def settings_get():
    """Return all settings intentionally exposed by the WireLoft UI."""
    return get_ui_settings()


@router.put("", response_model=SettingsAPIRead)
def settings_update(body: SettingsAPIUpdate):
    """Persist only explicitly changed UI fields into config.yml."""
    try:
        return save_ui_settings(body)
    except SettingsManagedByEnvironmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SettingsPersistenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
