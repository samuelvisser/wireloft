from fastapi import APIRouter, status

from .service import *
from ...models.media_profile import *

router = APIRouter()

@router.get("", response_model=list[MediaProfileAPIRead])
def media_profiles_list():
    return get_media_profiles_list()


@router.post("", response_model=MediaProfileAPIRead, status_code=status.HTTP_201_CREATED)
def media_profiles_create(body: MediaProfileAPICreate):
    return create_media_profile(body)


@router.get("/{media_profile_slug}", response_model=MediaProfileAPIRead)
def media_profiles_detail(media_profile_slug: str):
    return get_media_profile(media_profile_slug)


@router.patch("/{media_profile_slug}", response_model=MediaProfileAPIRead)
def media_profiles_update(media_profile_slug: str, body: MediaProfileAPIUpdate):
    return update_media_profile(media_profile_slug, body)


@router.delete("/{media_profile_slug}", response_model=MediaProfileAPIRead)
def media_profiles_delete(media_profile_slug: str):
    return delete_media_profile(media_profile_slug)