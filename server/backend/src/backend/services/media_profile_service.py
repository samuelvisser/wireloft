from backend.app import db_session
from backend.db.models import MediaProfile
from backend.api.schemas import MediaProfileItem
from flask import jsonify

def get_media_profiles_list():
    with db_session() as s:
        profiles = (
            s.query(MediaProfile)
            .order_by(MediaProfile.id)
            .all()
        )
        payload = [
            MediaProfileItem(
                id=str(mp.id),
                name=mp.name,
                output_template=mp.output_template,
                preferred_format=mp.preferred_format,
                download_series_images=bool(mp.download_series_images),
            ).model_dump()
            for mp in profiles
        ]
        return jsonify(payload)