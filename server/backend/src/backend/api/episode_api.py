from flask import Blueprint

from backend.services.episode import get_episode_list, get_episode

episode_api = Blueprint("episode_api", __name__)

episode_api.add_url_rule("/list", view_func=get_episode_list, methods=["GET"])
episode_api.add_url_rule("/<int:episode_id>", view_func=get_episode, methods=["GET"])
