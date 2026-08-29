from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from dailywire_api.records import (
    DwCatalogMoviePageRecord,
    DwCatalogRecord,
    DwCatalogShowPageRecord,
)

from .service import get_catalog, get_catalog_movies, get_catalog_shows

router = APIRouter(prefix="/catalog", tags=["DailyWire Catalog"])


@router.get("/shows", response_model=DwCatalogShowPageRecord)
def catalog_shows(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=60),
    search: str | None = None,
    grouping: Literal['host', 'alphabetical'] = 'host',
):
    try:
        return get_catalog_shows(offset=offset, limit=limit, search=search, grouping=grouping)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/movies", response_model=DwCatalogMoviePageRecord)
def catalog_movies(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=60),
    search: str | None = None,
):
    try:
        return get_catalog_movies(offset=offset, limit=limit, search=search)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("", response_model=DwCatalogRecord)
def catalog_detail():
    try:
        return get_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
