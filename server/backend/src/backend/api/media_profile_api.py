from flask import Blueprint

from backend.services.media_profile import get_media_profiles_list

media_profile_api = Blueprint("media_profile_api", __name__)

media_profile_api.add_url_rule("/list", view_func=get_media_profiles_list, methods=["GET"])