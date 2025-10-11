from fastapi import APIRouter, status

from .service import *
from ...models.local_media_profile import *
from backend.app import db_session

router = APIRouter(prefix="/local-media-profiles", tags=["Media Profiles"])

@router.get("", response_model=list[LocalMediaProfileAPIRead])
def local_media_profiles_list():
    """
    List all media profiles in the system.

    Returns a collection of all media profile configurations defining quality and format settings.
    """
    with db_session() as s:
        return get_local_media_profiles_list(s)


@router.post("", response_model=LocalMediaProfileAPIRead, status_code=status.HTTP_201_CREATED)
def local_media_profiles_create(body: LocalMediaProfileAPICreate):
    """
    Create a new media profile.

    Creates a new profile defining quality settings, resolution, and format preferences for media downloads.
    Returns the created profile with a generated slug identifier.
    """
    with db_session() as s:
        try:
            result = create_local_media_profile(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_detail(local_media_profile_slug: str):
    """
    Retrieve detailed information for a specific media profile.

    Returns complete profile configuration including quality settings and format preferences.
    """
    with db_session() as s:
        return get_local_media_profile(s, local_media_profile_slug)


@router.patch("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_update(local_media_profile_slug: str, body: LocalMediaProfileAPIUpdate):
    """
    Update an existing media profile's configuration.

    Partially updates profile settings with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
    with db_session() as s:
        try:
            result = update_local_media_profile(s, local_media_profile_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_delete(local_media_profile_slug: str):
    """
    Delete a media profile from the system.

    Permanently removes the specified profile configuration.
    Returns the deleted profile's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_local_media_profile(s, local_media_profile_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise