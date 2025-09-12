from __future__ import annotations

from fastapi import APIRouter, Header, Query, HTTPException

from dailywire_api.records import ShowRecord
from .service import get_show

router = APIRouter()


@router.get("/{show_slug}", response_model=ShowRecord)
def show_detail(
    show_slug: str,
    membership_plan: str | None = Query(default=None, description="Optional membership plan (e.g., AllAccess)"),
    authorization: str | None = Header(default=None, description="Optional Bearer token for premium content"),
):
    try:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
        return get_show(show_slug, access_token=token, membership_plan=membership_plan)
    except Exception as e:
        # Map any unhandled error to a 502 Bad Gateway since we're proxying upstream
        raise HTTPException(status_code=502, detail=str(e))
