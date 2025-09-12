from fastapi import HTTPException

from backend.api.models.response import SettingItemResponse
from backend.app import db_session
from backend.db.models import Settings

def get_settings_list() -> list[SettingItemResponse]:
    with db_session() as s:
        settings = (
            s.query(Settings)
            .order_by(Settings.id)
            .all()
        )
        payload = [
            SettingItemResponse.model_validate(setting, from_attributes=True)
            for setting in settings
        ]
        return payload

def get_setting(setting_slug: str) -> SettingItemResponse:
    with db_session() as s:
        setting = s.query(Settings).filter_by(slug=setting_slug).one_or_none()
        if setting is None:
            raise HTTPException(status_code=404, detail="Setting not found")

        payload = SettingItemResponse.model_validate(setting, from_attributes=True)

        return payload
