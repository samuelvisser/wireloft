from __future__ import annotations

from contextlib import contextmanager

from flask import Flask
from flask_cors import CORS

from backend.db import get_session

@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def create_app() -> Flask:
    app = Flask(__name__)

    # Allow the React dev server to call the API during development
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Import blueprints lazily to avoid circular imports during app module import
    from backend.api import media_profile_api, setting_api, show_api, meta_api

    app.register_blueprint(media_profile_api, url_prefix="/api/media-profile")
    app.register_blueprint(show_api, url_prefix="/api/show/<int:show_id>/episode")
    app.register_blueprint(show_api, url_prefix="/api/show")
    app.register_blueprint(setting_api, url_prefix="/api/setting")
    app.register_blueprint(meta_api, url_prefix="/api/meta")


    return app