from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import cast, Integer

from backend.db import get_session
from backend.db.models.MediaProfile import MediaProfile
from backend.db.models.Show import Show
from backend.db.models.Episode import Episode
from backend.db.models.Setting import Setting
from .records.SettingValueUpdate import SettingValueUpdate


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

    @app.get("/api/media-profiles")
    def get_media_profiles():
        with db_session() as s:
            profiles = (
                s.query(MediaProfile)
                .order_by(MediaProfile.id)
                .all()
            )
            payload = [
                {
                    "id": str(mp.id),
                    "name": mp.name,
                    "output_template": mp.output_template,
                    "preferred_format": mp.preferred_format,
                    "download_series_images": bool(mp.download_series_images),
                }
                for mp in profiles
            ]
            return jsonify(payload)

    @app.get("/api/shows")
    def get_shows():
        with db_session() as s:
            shows = (
                s.query(Show)
                .order_by(Show.id)
                .all()
            )
            payload = [
                {
                    "id": sh.slug,  # keep legacy behavior using slug as id in the list
                    "title": sh.title,
                    "author": sh.author_name,
                    "years": "unknown",
                }
                for sh in shows
            ]
            return jsonify(payload)

    @app.get("/api/shows/<show_id>")
    def get_show(show_id: str):
        with db_session() as s:
            show = s.query(Show).filter_by(slug=show_id).one_or_none()
            if show is None:
                return jsonify({"error": "Show not found"}), 404
            desc = show.description
            prefix = "Years: "
            years = desc[len(prefix):] if (isinstance(desc, str) and desc.startswith(prefix)) else desc
            payload = {
                "id": show.slug,
                "title": show.title,
                "author": show.author_name,
                "years": years,
            }
            return jsonify(payload)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/shows/<show_id>/episodes")
    def get_show_episodes(show_id: str):
        with db_session() as s:
            show = s.query(Show).filter_by(slug=show_id).one_or_none()
            if show is None:
                return jsonify({"error": "Show not found"}), 404
            episodes = (
                s.query(Episode)
                .filter_by(show_id=str(show.id))
                .order_by(cast(Episode.id, Integer))
                .all()
            )
            payload = [
                {
                    "id": (ep.slug or str(ep.id)),
                    "title": ep.title,
                    "index": (int(ep.id) if isinstance(ep.id, str) and ep.id.isdigit() else None),
                    "status": (ep.status or "downloaded"),
                }
                for ep in episodes
            ]
            return jsonify(payload)

    @app.get("/api/shows/<show_id>/episodes/<episode_slug>")
    def get_show_episode(show_id: str, episode_slug: str):
        with db_session() as s:
            show = s.query(Show).filter_by(slug=show_id).one_or_none()
            if show is None:
                return jsonify({"error": "Show not found"}), 404
            ep = (
                s.query(Episode)
                .filter_by(show_id=str(show.id), slug=episode_slug)
                .one_or_none()
            )
            if ep is None:
                return jsonify({"error": "Episode not found"}), 404
            payload = {
                "id": (ep.slug or str(ep.id)),
                "title": ep.title,
                "index": (int(ep.id) if isinstance(ep.id, str) and ep.id.isdigit() else None),
                "status": (ep.status or "downloaded"),
            }
            return jsonify(payload)

    @app.get("/api/settings/<slug>")
    def get_setting(slug: str):
        with db_session() as s:
            setting = s.query(Setting).filter_by(slug=slug).one_or_none()
            if setting is None:
                return jsonify({"error": "Setting not found"}), 404
            payload = {"slug": setting.slug, "name": setting.name, "value": setting.value}
            return jsonify(payload)

    @app.put("/api/settings/<slug>")
    def put_setting(slug: str):
        with db_session() as s:
            payload = request.get_json(silent=True) or {}
            update = SettingValueUpdate(**payload)
            now = datetime.now(timezone.utc)
            setting = s.query(Setting).filter_by(slug=slug).one_or_none()
            if setting is None:
                # Create new setting
                setting = Setting(
                    id=slug,
                    slug=slug,
                    name=slug,
                    value=update.value,
                    created_date=now,
                    modified_date=now,
                )
                s.add(setting)
            else:
                setting.value = update.value
                setting.modified_date = now
            s.commit()
            return jsonify({"slug": setting.slug, "name": setting.name, "value": setting.value})

    return app