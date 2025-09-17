from fastapi import APIRouter, status

from .service import *
from ...models.season import *

router = APIRouter()

@router.get("", response_model=list[SeasonAPIRead])
def seasons_list():
    return get_seasons_list()


@router.post("", response_model=SeasonAPIRead, status_code=status.HTTP_201_CREATED)
def seasons_create(body: SeasonAPICreate):
    return create_season(body)


@router.get("/{season_slug}", response_model=SeasonAPIRead)
def seasons_detail(season_slug: str):
    return get_season(season_slug)


@router.patch("/{season_slug}", response_model=SeasonAPIRead)
def seasons_update(season_slug: str, body: SeasonAPIUpdate):
    return update_season(season_slug, body)


@router.delete("/{season_slug}", response_model=SeasonAPIRead)
def seasons_delete(season_slug: str):
    return delete_season(season_slug)