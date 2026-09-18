from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from backend.api.models.custom_metadata import CustomMetadataAPIUpdate
from backend.api.models.movie import MovieAPIRead
from backend.api.models.show import ShowAPIRead
from backend.app import db_session
from backend.db.models import Show
from backend.db.models.media_item import Movie
from backend.utils.custom_metadata import (
    CustomMetadataScope,
    replace_custom_metadata,
)

from .service import (
    get_custom_metadata_fields,
    remove_shared_custom_metadata_fields,
)


router = APIRouter(tags=["Custom Metadata"])



@router.get("/custom-metadata/fields", response_model=list[str])
def custom_metadata_fields(
    scope: CustomMetadataScope = Query(...),
) -> list[str]:
    """List shared custom metadata field names for one media scope."""
    with db_session() as session:
        return get_custom_metadata_fields(session, scope)


@router.put("/shows/{show_slug}/metadata", response_model=ShowAPIRead)
def show_custom_metadata_update(show_slug: str, body: CustomMetadataAPIUpdate) -> ShowAPIRead:
    with db_session() as session:
        show = session.query(Show).filter_by(slug=show_slug).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        try:
            remove_shared_custom_metadata_fields(
                session,
                show,
                parent_table=Show.__tablename__,
                fields=body.removed_fields,
            )
            replace_custom_metadata(show, body.custom_metadata)
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
            remove_shared_custom_metadata_fields(
                session,
                movie,
                parent_table=Movie.__tablename__,
                fields=body.removed_fields,
            )
            replace_custom_metadata(movie, body.custom_metadata)
            session.flush()
            result = MovieAPIRead.model_validate(movie)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
