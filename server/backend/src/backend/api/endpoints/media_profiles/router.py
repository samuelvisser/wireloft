from fastapi import APIRouter, status

from .service import *
from ...models.media_profile import *
from backend.app import db_session

router = APIRouter(prefix="/media-profiles", tags=["Media Profiles"])

@router.get("", response_model=list[MediaProfileAPIRead])
def media_profiles_list():
    with db_session() as s:
        return get_media_profiles_list(s)


@router.post("", response_model=MediaProfileAPIRead, status_code=status.HTTP_201_CREATED)
def media_profiles_create(body: MediaProfileAPICreate):
    with db_session() as s:
        try:
            result = create_media_profile(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{media_profile_slug}", response_model=MediaProfileAPIRead)
def media_profiles_detail(media_profile_slug: str):
    with db_session() as s:
        return get_media_profile(s, media_profile_slug)


@router.patch("/{media_profile_slug}", response_model=MediaProfileAPIRead)
def media_profiles_update(media_profile_slug: str, body: MediaProfileAPIUpdate):
    with db_session() as s:
        try:
            result = update_media_profile(s, media_profile_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{media_profile_slug}", response_model=MediaProfileAPIRead)
def media_profiles_delete(media_profile_slug: str):
    with db_session() as s:
        try:
            result = delete_media_profile(s, media_profile_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise