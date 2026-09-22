from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.endpoints.local_media_profiles.helpers import ensure_unique_profile_settings
from backend.api.endpoints.local_media_profiles.service import delete_local_media_profile_record
from backend.api.models.movie_local_media_profile import (
    MovieLocalMediaProfileAPICreate,
    MovieLocalMediaProfileAPIRead,
    MovieLocalMediaProfileAPIUpdate,
)
from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.db.models import MovieLocalMediaProfile


def get_movie_local_media_profiles_list(
    s: Session,
) -> list[MovieLocalMediaProfileAPIRead]:
    items = (
        s.query(MovieLocalMediaProfile)
        .order_by(MovieLocalMediaProfile.id)
        .all()
    )
    return [MovieLocalMediaProfileAPIRead.model_validate(item) for item in items]


def get_movie_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> MovieLocalMediaProfileAPIRead:
    item: Optional[MovieLocalMediaProfile] = (
        s.query(MovieLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie Local Media Profile not found")
    return MovieLocalMediaProfileAPIRead.model_validate(item)


def create_movie_local_media_profile(
    s: Session,
    body: MovieLocalMediaProfileAPICreate,
) -> MovieLocalMediaProfileAPIRead:
    ensure_unique_profile_settings(s, MovieLocalMediaProfile, body)
    item = create_database_fields(MovieLocalMediaProfile, body)
    s.add(item)
    s.flush()
    return MovieLocalMediaProfileAPIRead.model_validate(item)


def update_movie_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
    body: MovieLocalMediaProfileAPIUpdate,
) -> MovieLocalMediaProfileAPIRead:
    item: Optional[MovieLocalMediaProfile] = (
        s.query(MovieLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie Local Media Profile not found")

    ensure_unique_profile_settings(
        s,
        MovieLocalMediaProfile,
        body,
        exclude_id=item.id,
    )
    update_database_fields(item, body)
    s.flush()
    return MovieLocalMediaProfileAPIRead.model_validate(item)


def delete_movie_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> MovieLocalMediaProfileAPIRead:
    item: Optional[MovieLocalMediaProfile] = (
        s.query(MovieLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie Local Media Profile not found")

    payload = MovieLocalMediaProfileAPIRead.model_validate(item)
    delete_local_media_profile_record(s, item)
    return payload
