from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException

from dailywire_api.records import DwShowRecord
from .service import get_show

router = APIRouter(prefix="/shows", tags=["DailyWire Shows"])


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
        return get_show(show_slug, membership_plan=membership_plan)
    except Exception as e:
        # Map any unhandled error to a 502 Bad Gateway since we're proxying upstream
        raise HTTPException(status_code=502, detail=str(e))
