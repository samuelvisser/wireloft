from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.models.custom_metadata import CustomMetadataAPIUpdate
from backend.api.models.download_profile import DownloadProfileAPIRead
from backend.api.models.movie import MovieAPIRead
from backend.api.models.show import ShowAPIRead
from backend.app import db_session
from backend.db.models import DownloadProfileBase, Show
from backend.db.models.media_item import Movie


router = APIRouter(tags=["Custom Metadata"])


def _replace_custom_metadata(resource, body: CustomMetadataAPIUpdate) -> None:
    resource.replace_custom_metadata(body.custom_metadata)


@router.put("/shows/{show_slug}/metadata", response_model=ShowAPIRead)
def show_custom_metadata_update(show_slug: str, body: CustomMetadataAPIUpdate) -> ShowAPIRead:
    with db_session() as session:
        show = session.query(Show).filter_by(slug=show_slug).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        try:
            _replace_custom_metadata(show, body)
            session.flush()
            result = ShowAPIRead.model_validate(show)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise


@router.put("/movies/{movie_slug}/metadata", response_model=MovieAPIRead)
def movie_custom_metadata_update(movie_slug: str, body: CustomMetadataAPIUpdate) -> MovieAPIRead:
    with db_session() as session:
        movie = session.query(Movie).filter_by(slug=movie_slug).one_or_none()
        if movie is None:
            raise HTTPException(status_code=404, detail="Movie not found")
        try:
            _replace_custom_metadata(movie, body)
            session.flush()
            result = MovieAPIRead.model_validate(movie)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise


@router.put("/download-profiles/{download_profile_id}/metadata", response_model=DownloadProfileAPIRead)
def download_profile_custom_metadata_update(
    download_profile_id: int,
    body: CustomMetadataAPIUpdate,
) -> DownloadProfileAPIRead:
    with db_session() as session:
        profile = session.get(DownloadProfileBase, download_profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Download profile not found")
        try:
            _replace_custom_metadata(profile, body)
            session.flush()
            result = DownloadProfileAPIRead.model_validate(profile)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
