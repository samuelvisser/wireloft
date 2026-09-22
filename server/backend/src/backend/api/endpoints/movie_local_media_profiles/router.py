from fastapi import APIRouter, status

from backend.api.models.movie_local_media_profile import (
    MovieLocalMediaProfileAPICreate,
    MovieLocalMediaProfileAPIRead,
    MovieLocalMediaProfileAPIUpdate,
)
from backend.app import db_session

from .service import (
    create_movie_local_media_profile,
    delete_movie_local_media_profile,
    get_movie_local_media_profile,
    get_movie_local_media_profiles_list,
    update_movie_local_media_profile,
)


router = APIRouter(
    prefix="/movie-local-media-profiles",
    tags=["Media Profiles (movie)"],
)


@router.get("", response_model=list[MovieLocalMediaProfileAPIRead])
def movie_local_media_profiles_list():
    with db_session() as s:
        return get_movie_local_media_profiles_list(s)


@router.post(
    "",
    response_model=MovieLocalMediaProfileAPIRead,
    status_code=status.HTTP_201_CREATED,
)
def movie_local_media_profiles_create(body: MovieLocalMediaProfileAPICreate):
    with db_session() as s:
        try:
            result = create_movie_local_media_profile(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get(
    "/{local_media_profile_slug}",
    response_model=MovieLocalMediaProfileAPIRead,
)
def movie_local_media_profiles_detail(local_media_profile_slug: str):
    with db_session() as s:
        return get_movie_local_media_profile(s, local_media_profile_slug)


@router.patch(
    "/{local_media_profile_slug}",
    response_model=MovieLocalMediaProfileAPIRead,
)
def movie_local_media_profiles_update(
    local_media_profile_slug: str,
    body: MovieLocalMediaProfileAPIUpdate,
):
    with db_session() as s:
        try:
            result = update_movie_local_media_profile(
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
    response_model=MovieLocalMediaProfileAPIRead,
)
def movie_local_media_profiles_delete(local_media_profile_slug: str):
    with db_session() as s:
        try:
            result = delete_movie_local_media_profile(s, local_media_profile_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
