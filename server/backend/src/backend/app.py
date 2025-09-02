from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS
from .dblegacy import connect_db
from .records.MediaProfileRecord import MediaProfileRecord
from .records.ShowRecord import ShowRecord
from .records.EpisodeRecord import EpisodeRecord
from .records.SettingRecord import SettingRecord
from .records.SettingValueUpdate import SettingValueUpdate

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
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, output_template, preferred_format, download_series_images FROM media_profiles ORDER BY id"
            )
            rows = cur.fetchall()
            records = [
                MediaProfileRecord(
                    id=str(r["id"]),
                    name=r["name"],
                    output_path_template=r["output_template"],
                    preferred_format=r["preferred_format"],
                    download_series_images=bool(r["download_series_images"]) if r["download_series_images"] is not None else False,
                )
                for r in rows
            ]
            return jsonify([rec.model_dump(by_alias=True) for rec in records])
        finally:
            conn.close()

    @app.get("/api/shows")
    def get_shows():
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT slug, name, author FROM shows ORDER BY id")
            rows = cur.fetchall()

            records = [
                ShowRecord(
                    id=r["slug"],
                    title=r["name"],
                    author=r["author"],
                    years="unknown",
                )
                for r in rows
            ]
            return jsonify([rec.model_dump(by_alias=True) for rec in records])
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
            desc = row["description"]
            prefix = "Years: "
            years = desc[len(prefix):] if (isinstance(desc, str) and desc.startswith(prefix)) else desc
            record = ShowRecord(
                id=row["slug"],
                title=row["name"],
                author=row["author"],
                years=years,
            )
            return jsonify(record.model_dump(by_alias=True))
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
            cur.execute("SELECT id FROM shows WHERE slug = ?", (show_id,))
            show_row = cur.fetchone()
            if show_row is None:
                return jsonify({"error": "Show not found"}), 404
            sid = show_row["id"]
            cur.execute(
                "SELECT id, slug, title, description FROM episodes WHERE show_id = ? ORDER BY id",
                (sid,),
            )
            rows = cur.fetchall()
            records = [
                EpisodeRecord(
                    id=(r["slug"] or str(r["id"])) ,
                    title=r["title"],
                    index=(int(r["id"]) if r["id"] is not None else None),
                    status=(r["description"] or "downloaded"),
                )
                for r in rows
            ]
            return jsonify([rec.model_dump(by_alias=True) for rec in records])
        finally:
            conn.close()

    @app.get("/api/shows/<show_id>/episodes/<episode_slug>")
    def get_show_episode(show_id: str, episode_slug: str):
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM shows WHERE slug = ?", (show_id,))
            show_row = cur.fetchone()
            if show_row is None:
                return jsonify({"error": "Show not found"}), 404
            sid = show_row["id"]
            cur.execute(
                "SELECT id, slug, title, description FROM episodes WHERE show_id = ? AND slug = ?",
                (sid, episode_slug),
            )
            r = cur.fetchone()
            if r is None:
                return jsonify({"error": "Episode not found"}), 404
            record = EpisodeRecord(
                id=(r["slug"] or str(r["id"])) ,
                title=r["title"],
                index=(int(r["id"]) if r["id"] is not None else None),
                status=(r["description"] or "downloaded"),
            )
            return jsonify(record.model_dump(by_alias=True))
        finally:
            conn.close()

    @app.get("/api/settings/<slug>")
    def get_setting(slug: str):
        conn = connect_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT slug, name, value FROM settings WHERE slug = ?",
                (slug,),
            )
            row = cur.fetchone()
            if row is None:
                return jsonify({"error": "Setting not found"}), 404
            record = SettingRecord(slug=row["slug"], name=row["name"], value=row["value"])
            return jsonify(record.model_dump(by_alias=True))
        finally:
            conn.close()

    @app.put("/api/settings/<slug>")
    def put_setting(slug: str):
        conn = connect_db()
        try:
            payload = request.get_json(silent=True) or {}
            update = SettingValueUpdate(**payload)
            cur = conn.cursor()
            # Check existing
            cur.execute("SELECT id, name FROM settings WHERE slug = ?", (slug,))
            row = cur.fetchone()
            now_val = update.value
            now_str = __import__("datetime").datetime.utcnow().isoformat(timespec="seconds")
            if row is None:
                # Insert new setting with name = slug if no name known
                cur.execute(
                    "INSERT INTO settings (slug, name, value, created_date, modified_date) VALUES (?, ?, ?, ?, ?)",
                    (slug, slug, now_val, now_str, now_str),
                )
            else:
                cur.execute(
                    "UPDATE settings SET value = ?, modified_date = ? WHERE slug = ?",
                    (now_val, now_str, slug),
                )
            conn.commit()
            # Return the updated record
            cur.execute("SELECT slug, name, value FROM settings WHERE slug = ?", (slug,))
            r2 = cur.fetchone()
            record = SettingRecord(slug=r2["slug"], name=r2["name"], value=r2["value"])
            return jsonify(record.model_dump(by_alias=True))
        finally:
            conn.close()

    return app