from fastapi import APIRouter

from backend.services.media_profile.service import get_media_profiles_list, get_media_profile
from backend.services.media_profile.response_models import MediaProfileItemResponse

router = APIRouter()

@router.get("", response_model=list[MediaProfileItemResponse])
def media_profiles_list():
    return get_media_profiles_list()

@router.post("", response_model=MediaProfileItemResponse)
def media_profiles_create():
    # Create a media profile
    ...

@router.get("/{media_profile_slug}", response_model=MediaProfileItemResponse)
def media_profiles_detail(media_profile_slug: str):
    return get_media_profile(media_profile_slug)

@router.patch("/{media_profile_slug}", response_model=MediaProfileItemResponse)
def media_profiles_update(media_profile_slug: str):
    # Update the media profile
    ...

@router.delete("/{media_profile_slug}", response_model=MediaProfileItemResponse)
def media_profiles_delete(media_profile_slug: str):
    # Delete the media profile
    ...