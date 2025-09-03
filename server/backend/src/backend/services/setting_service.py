from backend.app import db_session
from flask import jsonify

from backend.db.models import Setting



def get_setting(id: int):
    with db_session() as s:
        setting = s.query(Setting).filter_by(id=id).one_or_none()
        if setting is None:
            return jsonify({"error": "Setting not found"}), 404
        payload = {"slug": setting.slug, "name": setting.name, "value": setting.value}
        return jsonify(payload)
