from fastapi import APIRouter

from backend.services.media_profile.service import get_media_profiles_list
from backend.services.media_profile.response_models import MediaProfileItemResponse

router = APIRouter()

@router.get("/list", response_model=list[MediaProfileItemResponse])
def media_profiles_list():
    return get_media_profiles_list()