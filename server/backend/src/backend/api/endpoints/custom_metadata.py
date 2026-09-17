from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.api.models.custom_metadata import CustomMetadataAPIUpdate
from backend.api.models.movie import MovieAPIRead
from backend.api.models.show import ShowAPIRead
from backend.app import db_session
from backend.db.models import Show
from backend.db.models.Metadata import Metadata
from backend.db.models.media_item import Movie
from backend.utils.custom_metadata import custom_metadata_storage_key


router = APIRouter(tags=["Custom Metadata"])


def _remove_shared_fields(
    session: Session,
    resource,
    *,
    parent_table: str,
    fields: list[str],
) -> None:
    """Delete a field and all of its values for one metadata owner type."""
    if not fields:
        return

    storage_keys = [custom_metadata_storage_key(key) for key in fields]
    session.execute(
        delete(Metadata).where(
            Metadata.parent_table == parent_table,
            Metadata.key.in_(storage_keys),
        )
    )
    session.flush()
    # HasMetadataMixin uses a selectin-loaded collection. Reload the current
    # resource before replacing its remaining values so globally deleted rows
    # cannot be reintroduced from a stale relationship collection.
    session.expire(resource, ["meta_items"])


def _replace_custom_metadata(resource, body: CustomMetadataAPIUpdate) -> None:
    resource.replace_custom_metadata(body.custom_metadata)


@router.put("/shows/{show_slug}/metadata", response_model=ShowAPIRead)
def show_custom_metadata_update(show_slug: str, body: CustomMetadataAPIUpdate) -> ShowAPIRead:
    with db_session() as session:
        show = session.query(Show).filter_by(slug=show_slug).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        try:
            _remove_shared_fields(
                session,
                show,
                parent_table=Show.__tablename__,
                fields=body.removed_fields,
            )
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
            _remove_shared_fields(
                session,
                movie,
                parent_table=Movie.__tablename__,
                fields=body.removed_fields,
            )
            _replace_custom_metadata(movie, body)
            session.flush()
            result = MovieAPIRead.model_validate(movie)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
