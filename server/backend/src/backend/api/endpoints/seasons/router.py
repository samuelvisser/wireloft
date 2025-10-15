from fastapi import APIRouter, status

from .service import *
from ...models.season import *
from backend.app import db_session

router = APIRouter(prefix="/shows/{show_slug}/seasons", tags=["Seasons"])

@router.get("", response_model=list[SeasonAPIRead])
def season_list(show_slug: str):
    """
    List all seasons for a specific show.

    Returns a collection of all seasons associated with the specified show slug.
    """
    with db_session() as s:
        return get_seasons_list(s, show_slug)


@router.post("", response_model=SeasonAPIRead, status_code=status.HTTP_201_CREATED)
def season_create(body: SeasonAPICreate):
    """
    Create a new season for a show.

    Creates a new season with the provided metadata and associates it with a show.
    Returns the created season with a generated slug identifier.
    """
    with db_session() as s:
        try:
            result = create_season(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{season_slug}", response_model=SeasonAPIRead)
def season_detail(show_slug: str, season_slug: str):
    """
    Retrieve detailed information for a specific season.

    Returns complete season metadata including title, number, and associated episodes.
    """
    with db_session() as s:
        return get_season(s, show_slug, season_slug)


@router.patch("/{season_slug}", response_model=SeasonAPIRead)
def season_update(show_slug: str, season_slug: str, body: SeasonAPIUpdate):
    """
    Update an existing season's metadata.

    Partially updates season information with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
    with db_session() as s:
        try:
            result = update_season(s, show_slug, season_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{season_slug}", response_model=SeasonAPIRead)
def season_delete(show_slug: str, season_slug: str):
    """
    Delete a season from the system.

    Permanently removes the specified season and its associated data.
    Returns the deleted season's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_season(s, show_slug, season_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise