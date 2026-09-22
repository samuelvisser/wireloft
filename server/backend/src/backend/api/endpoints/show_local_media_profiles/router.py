from fastapi import APIRouter, status

from backend.api.models.operations import LocalMediaProfileFileRenameOperationAccepted
from backend.api.models.show_local_media_profile import (
    ShowLocalMediaProfileAPICreate,
    ShowLocalMediaProfileAPIRead,
    ShowLocalMediaProfileAPIUpdate,
)
from backend.app import db_session
from backend.api.endpoints.local_media_profiles.file_rename import (
    request_show_local_media_profile_file_rename,
)

from .service import (
    create_show_local_media_profile,
    delete_show_local_media_profile,
    get_show_local_media_profile,
    get_show_local_media_profiles_list,
    update_show_local_media_profile,
)


router = APIRouter(
    prefix="/show-local-media-profiles",
    tags=["Media Profiles (show)"],
)


@router.get("", response_model=list[ShowLocalMediaProfileAPIRead])
def show_local_media_profiles_list():
    with db_session() as s:
        return get_show_local_media_profiles_list(s)


@router.post(
    "",
    response_model=ShowLocalMediaProfileAPIRead,
    status_code=status.HTTP_201_CREATED,
)
def show_local_media_profiles_create(body: ShowLocalMediaProfileAPICreate):
    with db_session() as s:
        try:
            result = create_show_local_media_profile(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{local_media_profile_slug}/rename-files",
    response_model=LocalMediaProfileFileRenameOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def show_local_media_profile_rename_files(local_media_profile_slug: str):
    with db_session() as s:
        try:
            result = request_show_local_media_profile_file_rename(s, local_media_profile_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get(
    "/{local_media_profile_slug}",
    response_model=ShowLocalMediaProfileAPIRead,
)
def show_local_media_profiles_detail(local_media_profile_slug: str):
    with db_session() as s:
        return get_show_local_media_profile(s, local_media_profile_slug)


@router.patch(
    "/{local_media_profile_slug}",
    response_model=ShowLocalMediaProfileAPIRead,
)
def show_local_media_profiles_update(
    local_media_profile_slug: str,
    body: ShowLocalMediaProfileAPIUpdate,
):
    with db_session() as s:
        try:
            result = update_show_local_media_profile(
                s,
                local_media_profile_slug,
                body,
            )
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete(
    "/{local_media_profile_slug}",
    response_model=ShowLocalMediaProfileAPIRead,
)
def show_local_media_profiles_delete(local_media_profile_slug: str):
    with db_session() as s:
        try:
            result = delete_show_local_media_profile(s, local_media_profile_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
