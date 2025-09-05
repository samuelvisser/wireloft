from fastapi import APIRouter

from .service import *
from ...models.request import MediaProfileCreateBody, MediaProfileUpdateBody
from ...models.response import MediaProfileItemResponse

router = APIRouter()

@router.get("", response_model=list[MediaProfileItemResponse])
def media_profiles_list():
    return get_media_profiles_list()


@router.post("", response_model=MediaProfileItemResponse)
def media_profiles_create(body: MediaProfileCreateBody):
    return create_media_profile(**body.model_dump())


@router.get("/{media_profile_slug}", response_model=MediaProfileItemResponse)
def media_profiles_detail(media_profile_slug: str):
    return get_media_profile(media_profile_slug)


@router.patch("/{media_profile_slug}", response_model=MediaProfileItemResponse)
def media_profiles_update(media_profile_slug: str, body: MediaProfileUpdateBody):
    return update_media_profile(media_profile_slug, **body.model_dump(exclude_unset=True))


@router.delete("/{media_profile_slug}", response_model=MediaProfileItemResponse)
def media_profiles_delete(media_profile_slug: str):
    return delete_media_profile(media_profile_slug)