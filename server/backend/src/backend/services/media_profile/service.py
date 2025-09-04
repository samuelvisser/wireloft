from backend.app import db_session
from backend.db.models import MediaProfile
from .response_models import MediaProfileItemResponse


def get_media_profiles_list() -> list[MediaProfileItemResponse]:
    with db_session() as s:
        profiles = (
            s.query(MediaProfile)
            .order_by(MediaProfile.id)
            .all()
        )
        payload = [
            MediaProfileItemResponse(
                id=str(mp.id),
                name=mp.name,
                output_template=mp.output_template,
                preferred_format=mp.preferred_format,
                download_series_images=bool(mp.download_series_images),
            )
            for mp in profiles
        ]
        return payload
