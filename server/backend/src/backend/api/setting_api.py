from fastapi import APIRouter

from backend.services.setting.service import get_setting
from backend.services.setting.response_models import SettingItem

router = APIRouter()

@router.get("/{setting_id}", response_model=SettingItem)
def setting_detail(setting_id: int):
    return get_setting(setting_id)