from fastapi import HTTPException

from backend.app import db_session
from backend.db.models import Setting
from .response_models import SettingItemResponse


def get_settings_list() -> list[SettingItemResponse]:
    with db_session() as s:
        settings = (
            s.query(Setting)
            .order_by(Setting.id)
            .all()
        )
        payload = [
            SettingItemResponse.model_validate(setting, from_attributes=True)
            for setting in settings
        ]
        return payload

def get_setting(setting_slug: str) -> SettingItemResponse:
    with db_session() as s:
        setting = s.query(Setting).filter_by(slug=setting_slug).one_or_none()
        if setting is None:
            raise HTTPException(status_code=404, detail="Setting not found")

        payload = SettingItemResponse.model_validate(setting, from_attributes=True)

        return payload
