from fastapi import APIRouter, status

from .service import *
from ...models.season import *
from backend.app import db_session

router = APIRouter(prefix="/seasons", tags=["Seasons"])

@router.get("", response_model=list[SeasonAPIRead])
def seasons_list():
    """
    List all seasons in the system.

    Returns a collection of all season records across all shows.
    """
    with db_session() as s:
        return get_seasons_list(s)


@router.post("", response_model=SeasonAPIRead, status_code=status.HTTP_201_CREATED)
def seasons_create(body: SeasonAPICreate):
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
def seasons_detail(season_slug: str):
    """
    Retrieve detailed information for a specific season.

    Returns complete season metadata including title, number, and associated episodes.
    """
    with db_session() as s:
        return get_season(s, season_slug)


@router.patch("/{season_slug}", response_model=SeasonAPIRead)
def seasons_update(season_slug: str, body: SeasonAPIUpdate):
    """
    Update an existing season's metadata.

    Partially updates season information with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
    with db_session() as s:
        try:
            result = update_season(s, season_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{season_slug}", response_model=SeasonAPIRead)
def seasons_delete(season_slug: str):
    """
    Delete a season from the system.

    Permanently removes the specified season and its associated data.
    Returns the deleted season's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_season(s, season_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise