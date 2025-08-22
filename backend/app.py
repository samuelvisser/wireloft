from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS


def create_app() -> Flask:
    app = Flask(__name__)

    # Allow the React dev server to call the API during development
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Hardcoded media profiles (moved from React UI)
    media_profiles = [
        {
            "id": "p1",
            "name": "Default 1080p",
            "outputPathTemplate": "D:/Media/Shows/{show}/{season}",
            "preferredFormat": "1080p",
            "downloadSeriesImages": True,
        },
        {
            "id": "p2",
            "name": "Mobile 720p backend",
            "outputPathTemplate": "E:/Mobile/Shows/{show}",
            "preferredFormat": "720p",
            "downloadSeriesImages": False,
        },
    ]

    @app.get("/api/media-profiles")
    def get_media_profiles():
        return jsonify(media_profiles)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
