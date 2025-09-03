from backend.app import db_session
from flask import jsonify

from backend.db.models import Setting
from backend.api.schemas import SettingItem, ErrorResponse


def get_setting(id: int):
    with db_session() as s:
        setting = s.query(Setting).filter_by(id=id).one_or_none()
        if setting is None:
            return jsonify(ErrorResponse(error="Setting not found").model_dump()), 404
        payload = SettingItem(slug=setting.slug, name=setting.name, value=setting.value).model_dump()
        return jsonify(payload)
