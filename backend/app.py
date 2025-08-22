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

    # Hardcoded shows and episodes (no randomness)
    shows = [
        {
            "id": "the-ben-shapiro-show",
            "author": "Ben Shapiro",
            "title": "The Ben Shapiro Show",
            "years": "2015-2025",
            "episodes": [
                {"id": "the-ben-shapiro-show-1", "title": "The Ben Shapiro Show — Episode 1", "index": 1, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-2", "title": "The Ben Shapiro Show — Episode 2", "index": 2, "status": "downloading"},
                {"id": "the-ben-shapiro-show-3", "title": "The Ben Shapiro Show — Episode 3", "index": 3, "status": "processing"},
                {"id": "the-ben-shapiro-show-4", "title": "The Ben Shapiro Show — Episode 4", "index": 4, "status": "error"},
                {"id": "the-ben-shapiro-show-5", "title": "The Ben Shapiro Show — Episode 5", "index": 5, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-6", "title": "The Ben Shapiro Show — Episode 6", "index": 6, "status": "downloading"},
                {"id": "the-ben-shapiro-show-7", "title": "The Ben Shapiro Show — Episode 7", "index": 7, "status": "processing"},
                {"id": "the-ben-shapiro-show-8", "title": "The Ben Shapiro Show — Episode 8", "index": 8, "status": "error"},
                {"id": "the-ben-shapiro-show-9", "title": "The Ben Shapiro Show — Episode 9", "index": 9, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-10", "title": "The Ben Shapiro Show — Episode 10", "index": 10, "status": "downloading"},
                {"id": "the-ben-shapiro-show-11", "title": "The Ben Shapiro Show — Episode 11", "index": 11, "status": "processing"},
                {"id": "the-ben-shapiro-show-12", "title": "The Ben Shapiro Show — Episode 12", "index": 12, "status": "error"},
                {"id": "the-ben-shapiro-show-13", "title": "The Ben Shapiro Show — Episode 13", "index": 13, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-14", "title": "The Ben Shapiro Show — Episode 14", "index": 14, "status": "downloading"},
                {"id": "the-ben-shapiro-show-15", "title": "The Ben Shapiro Show — Episode 15", "index": 15, "status": "processing"},
                {"id": "the-ben-shapiro-show-16", "title": "The Ben Shapiro Show — Episode 16", "index": 16, "status": "error"},
                {"id": "the-ben-shapiro-show-17", "title": "The Ben Shapiro Show — Episode 17", "index": 17, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-18", "title": "The Ben Shapiro Show — Episode 18", "index": 18, "status": "downloading"},
                {"id": "the-ben-shapiro-show-19", "title": "The Ben Shapiro Show — Episode 19", "index": 19, "status": "processing"},
                {"id": "the-ben-shapiro-show-20", "title": "The Ben Shapiro Show — Episode 20", "index": 20, "status": "error"},
                {"id": "the-ben-shapiro-show-21", "title": "The Ben Shapiro Show — Episode 21", "index": 21, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-22", "title": "The Ben Shapiro Show — Episode 22", "index": 22, "status": "downloading"},
                {"id": "the-ben-shapiro-show-23", "title": "The Ben Shapiro Show — Episode 23", "index": 23, "status": "processing"},
                {"id": "the-ben-shapiro-show-24", "title": "The Ben Shapiro Show — Episode 24", "index": 24, "status": "error"},
                {"id": "the-ben-shapiro-show-25", "title": "The Ben Shapiro Show — Episode 25", "index": 25, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-26", "title": "The Ben Shapiro Show — Episode 26", "index": 26, "status": "downloading"},
                {"id": "the-ben-shapiro-show-27", "title": "The Ben Shapiro Show — Episode 27", "index": 27, "status": "processing"},
                {"id": "the-ben-shapiro-show-28", "title": "The Ben Shapiro Show — Episode 28", "index": 28, "status": "error"},
                {"id": "the-ben-shapiro-show-29", "title": "The Ben Shapiro Show — Episode 29", "index": 29, "status": "downloaded"},
                {"id": "the-ben-shapiro-show-30", "title": "The Ben Shapiro Show — Episode 30", "index": 30, "status": "downloading"},
            ],
        },
        {
            "id": "the-matt-walsh-show",
            "author": "Matt Walsh",
            "title": "The Matt Walsh Show",
            "years": "2018 – 2025",
            "episodes": [
                {"id": "the-matt-walsh-show-1", "title": "The Matt Walsh Show — Episode 1", "index": 1, "status": "processing"},
                {"id": "the-matt-walsh-show-2", "title": "The Matt Walsh Show — Episode 2", "index": 2, "status": "error"},
                {"id": "the-matt-walsh-show-3", "title": "The Matt Walsh Show — Episode 3", "index": 3, "status": "downloaded"},
                {"id": "the-matt-walsh-show-4", "title": "The Matt Walsh Show — Episode 4", "index": 4, "status": "downloading"},
                {"id": "the-matt-walsh-show-5", "title": "The Matt Walsh Show — Episode 5", "index": 5, "status": "processing"},
                {"id": "the-matt-walsh-show-6", "title": "The Matt Walsh Show — Episode 6", "index": 6, "status": "error"},
                {"id": "the-matt-walsh-show-7", "title": "The Matt Walsh Show — Episode 7", "index": 7, "status": "downloaded"},
                {"id": "the-matt-walsh-show-8", "title": "The Matt Walsh Show — Episode 8", "index": 8, "status": "downloading"},
                {"id": "the-matt-walsh-show-9", "title": "The Matt Walsh Show — Episode 9", "index": 9, "status": "processing"},
                {"id": "the-matt-walsh-show-10", "title": "The Matt Walsh Show — Episode 10", "index": 10, "status": "error"},
                {"id": "the-matt-walsh-show-11", "title": "The Matt Walsh Show — Episode 11", "index": 11, "status": "downloaded"},
                {"id": "the-matt-walsh-show-12", "title": "The Matt Walsh Show — Episode 12", "index": 12, "status": "downloading"},
                {"id": "the-matt-walsh-show-13", "title": "The Matt Walsh Show — Episode 13", "index": 13, "status": "processing"},
                {"id": "the-matt-walsh-show-14", "title": "The Matt Walsh Show — Episode 14", "index": 14, "status": "error"},
                {"id": "the-matt-walsh-show-15", "title": "The Matt Walsh Show — Episode 15", "index": 15, "status": "downloaded"},
                {"id": "the-matt-walsh-show-16", "title": "The Matt Walsh Show — Episode 16", "index": 16, "status": "downloading"},
                {"id": "the-matt-walsh-show-17", "title": "The Matt Walsh Show — Episode 17", "index": 17, "status": "processing"},
                {"id": "the-matt-walsh-show-18", "title": "The Matt Walsh Show — Episode 18", "index": 18, "status": "error"},
                {"id": "the-matt-walsh-show-19", "title": "The Matt Walsh Show — Episode 19", "index": 19, "status": "downloaded"},
                {"id": "the-matt-walsh-show-20", "title": "The Matt Walsh Show — Episode 20", "index": 20, "status": "downloading"},
            ],
        },
        {
            "id": "ben-after-dark",
            "author": "Ben Shapiro",
            "title": "Ben After Dark",
            "years": "2025 - 2025",
            "episodes": [
                {"id": "ben-after-dark-1", "title": "Ben After Dark — Episode 1", "index": 1, "status": "processing"},
                {"id": "ben-after-dark-2", "title": "Ben After Dark — Episode 2", "index": 2, "status": "error"},
                {"id": "ben-after-dark-3", "title": "Ben After Dark — Episode 3", "index": 3, "status": "downloaded"},
                {"id": "ben-after-dark-4", "title": "Ben After Dark — Episode 4", "index": 4, "status": "downloading"},
                {"id": "ben-after-dark-5", "title": "Ben After Dark — Episode 5", "index": 5, "status": "processing"},
                {"id": "ben-after-dark-6", "title": "Ben After Dark — Episode 6", "index": 6, "status": "error"},
                {"id": "ben-after-dark-7", "title": "Ben After Dark — Episode 7", "index": 7, "status": "downloaded"},
            ],
        },
    ]

    @app.get("/api/media-profiles")
    def get_media_profiles():
        return jsonify(media_profiles)

    @app.get("/api/shows")
    def get_shows():
        return jsonify(shows)

    @app.get("/api/shows/<show_id>")
    def get_show(show_id: str):
        for s in shows:
            if s["id"] == show_id:
                return jsonify(s)
        return jsonify({"error": "Show not found"}), 404

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
