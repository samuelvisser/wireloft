from flask import Blueprint

from backend.services.meta import health

meta_api = Blueprint("meta_api", __name__)

meta_api.add_url_rule("/health", view_func=health, methods=["GET"])
