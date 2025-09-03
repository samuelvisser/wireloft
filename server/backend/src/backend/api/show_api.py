from flask import Blueprint

from backend.services.show import get_show_list, get_show

show_api = Blueprint("show_api", __name__)

show_api.add_url_rule("/list", view_func=get_show_list, methods=["GET"])
show_api.add_url_rule("/<int:show_id>", view_func=get_show, methods=["GET"])