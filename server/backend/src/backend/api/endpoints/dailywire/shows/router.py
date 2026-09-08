from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException

from backend.api.datetime import api_timezone_payload
from dailywire_api.records import DwShowRecord
from dailywire_api.records.DwShowRecord import ProbableShowType
from .service import get_show, get_show_type_classifications

router = APIRouter(prefix="/shows", tags=["DailyWire Shows"])


@router.post("/classifications", response_model=dict[str, ProbableShowType])
def show_type_classifications(show_slugs: list[str]):
    """Classify catalog shows with the same best-effort model used by Add Show."""
    try:
        return get_show_type_classifications(show_slugs)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{show_slug}", response_model=DwShowRecord)
def show_detail(
    show_slug: str,
    membership_plan: str | None = Query(default=None, description="Optional membership plan (e.g., ALL_ACCESS)"),
):
    """
    Retrieve show information from DailyWire API.

    Fetches show metadata directly from the DailyWire upstream API.
    Supports authentication via Bearer token for premium content access.
    Returns 502 if upstream API is unavailable or returns an error.
    """
    try:
        return api_timezone_payload(get_show(show_slug, membership_plan=membership_plan))
    except Exception as e:
        # Map any unhandled error to a 502 Bad Gateway since we're proxying upstream
        raise HTTPException(status_code=502, detail=str(e))
