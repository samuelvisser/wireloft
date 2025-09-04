from fastapi import APIRouter

from backend.services.setting.service import get_setting, get_settings_list
from backend.services.setting.response_models import SettingItemResponse

router = APIRouter()


@router.get("", response_model=list[SettingItemResponse])
def settings_list():
    return get_settings_list()

@router.post("", response_model=SettingItemResponse)
def settings_create():
    # Create a setting
    ...


@router.get("/{setting_slug}", response_model=SettingItemResponse)
def setting_detail(setting_slug: str):
    return get_setting(setting_slug)

@router.patch("/{setting_slug}", response_model=SettingItemResponse)
def setting_update(setting_slug: str):
    # Update the setting
    ...

@router.delete("/{setting_slug}", response_model=SettingItemResponse)
def setting_delete(setting_slug: str):
    # Delete the setting
    ...