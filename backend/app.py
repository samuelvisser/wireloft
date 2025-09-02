from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS
from .db import connect_db


def create_app() -> Flask:
    app = Flask(__name__)

    # Enforce DB presence on startup
    try:
        conn = connect_db()
        conn.close()
    except FileNotFoundError as e:
        # Re-raise to fail fast if DB is missing
        raise

    # Allow the React dev server to call the API during development
    CORS(app, resources={r"/api/*": {"origins": "*"}})


    @app.get("/api/media-profiles")
    def get_media_profiles():
        # Return media profiles from DB
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, output_template, preferred_format, download_series_images FROM media_profiles ORDER BY id"
            )
            rows = cur.fetchall()
            result = [
                {
                    "id": str(r["id"]),
                    "name": r["name"],
                    "outputPathTemplate": r["output_template"],
                    "preferredFormat": r["preferred_format"],
                    "downloadSeriesImages": bool(r["download_series_images"]) if r["download_series_images"] is not None else False,
                }
                for r in rows
            ]
            return jsonify(result)
        finally:
            conn.close()

    @app.get("/api/shows")
    def get_shows():
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT slug, title, author FROM shows ORDER BY id")
            rows = cur.fetchall()

            result = [
                {
                    "id": r["slug"],
                    "author": r["author"],
                    "title": r["title"],
                    "years": "unknown",
                }
                for r in rows
            ]
            return jsonify(result)
        finally:
            conn.close()

    @app.get("/api/shows/<show_id>")
    def get_show(show_id: str):
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT slug, name, author, description FROM shows WHERE slug = ?",
                (show_id,),
            )
            row = cur.fetchone()
            if row is None:
                return jsonify({"error": "Show not found"}), 404
            # Derive years from description if prefixed
            desc = row["description"]
            prefix = "Years: "
            years = desc[len(prefix):] if (isinstance(desc, str) and desc.startswith(prefix)) else desc
            return jsonify({
                "id": row["slug"],
                "author": row["author"],
                "title": row["name"],
                "years": years,
            })
        finally:
            conn.close()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/shows/<show_id>/episodes")
    def get_show_episodes(show_id: str):
        conn = connect_db()
        try:
            cur = conn.cursor()
            # Ensure show exists and get its numeric id
            cur.execute("SELECT id FROM shows WHERE slug = ?", (show_id,))
            show_row = cur.fetchone()
            if show_row is None:
                return jsonify({"error": "Show not found"}), 404
            sid = show_row["id"]
            # Load episodes for the show
            cur.execute(
                "SELECT id, slug, title, description FROM episodes WHERE show_id = ? ORDER BY id",
                (sid,),
            )
            rows = cur.fetchall()
            result = [
                {
                    "id": r["slug"] or str(r["id"]),
                    "title": r["title"],
                    "index": int(r["id"]) if r["id"] is not None else None,
                    "status": (r["description"] or "downloaded"),
                }
                for r in rows
            ]
            return jsonify(result)
        finally:
            conn.close()

    @app.get("/api/shows/<show_id>/episodes/<episode_slug>")
    def get_show_episode(show_id: str, episode_slug: str):
        conn = connect_db()
        try:
            cur = conn.cursor()
            # Validate show
            cur.execute("SELECT id FROM shows WHERE slug = ?", (show_id,))
            show_row = cur.fetchone()
            if show_row is None:
                return jsonify({"error": "Show not found"}), 404
            sid = show_row["id"]
            # Find episode by slug within this show
            cur.execute(
                "SELECT id, slug, title, description FROM episodes WHERE show_id = ? AND slug = ?",
                (sid, episode_slug),
            )
            r = cur.fetchone()
            if r is None:
                return jsonify({"error": "Episode not found"}), 404
            ep = {
                "id": r["slug"] or str(r["id"]),
                "title": r["title"],
                "index": int(r["id"]) if r["id"] is not None else None,
                "status": (r["description"] or "downloaded"),
            }
            return jsonify(ep)
        finally:
            conn.close()

    return app
