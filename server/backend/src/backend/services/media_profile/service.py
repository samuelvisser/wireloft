from backend.app import db_session
from backend.db.models import MediaProfile
from .response_models import MediaProfileItemResponse
from fastapi import HTTPException


def get_media_profiles_list() -> list[MediaProfileItemResponse]:
    with db_session() as s:
        profiles = (
            s.query(MediaProfile)
            .order_by(MediaProfile.id)
            .all()
        )
        payload = [
            MediaProfileItemResponse.model_validate(mp, from_attributes=True)
            for mp in profiles
        ]
        return payload

def get_media_profile(media_profile_slug: str) -> MediaProfileItemResponse:
    with db_session() as s:
        profile = s.query(MediaProfile).filter_by(slug=media_profile_slug).one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        payload = MediaProfileItemResponse.model_validate(profile, from_attributes=True)
        return payload
