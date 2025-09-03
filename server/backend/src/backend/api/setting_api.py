from flask import Blueprint
from backend.services.setting_service import get_setting


setting_api = Blueprint("setting_api", __name__)

setting_api.add_url_rule("/<int:setting_id>", view_func=get_setting, methods=["GET"])