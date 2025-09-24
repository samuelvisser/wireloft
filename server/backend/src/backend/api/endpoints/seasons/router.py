from fastapi import APIRouter, status

from .service import *
from ...models.season import *
from ...app import db_session

router = APIRouter()

@router.get("", response_model=list[SeasonAPIRead])
def seasons_list():
    with db_session() as s:
        return get_seasons_list(s)


@router.post("", response_model=SeasonAPIRead, status_code=status.HTTP_201_CREATED)
def seasons_create(body: SeasonAPICreate):
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
    with db_session() as s:
        return get_season(s, season_slug)


@router.patch("/{season_slug}", response_model=SeasonAPIRead)
def seasons_update(season_slug: str, body: SeasonAPIUpdate):
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
    with db_session() as s:
        try:
            result = delete_season(s, season_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise