from fastapi import APIRouter, HTTPException

from dailywire_api.records import DwCatalogRecord

from .service import get_catalog

router = APIRouter(prefix="/catalog", tags=["DailyWire Catalog"])


@router.get("", response_model=DwCatalogRecord)
def catalog_detail():
    try:
        return get_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
