from fastapi import HTTPException

from backend.app import db_session
from backend.db.models import Setting
from .response_models import SettingItem


def get_setting(setting_id: int) -> SettingItem:
    with db_session() as s:
        setting = s.query(Setting).filter_by(id=setting_id).one_or_none()
        if setting is None:
            raise HTTPException(status_code=404, detail="Setting not found")

        payload = SettingItem(slug=setting.slug, name=setting.name, value=setting.value)
        return payload
