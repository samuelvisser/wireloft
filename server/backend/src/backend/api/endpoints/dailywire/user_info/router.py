from __future__ import annotations

from fastapi import APIRouter, HTTPException

from dailywire_api.records.UserInfo import UserInfo
from .service import get_user_info

router = APIRouter(prefix="/user-info", tags=["DailyWire User"])


@router.get("", response_model=UserInfo)
def user_info():
    """
    Return the current user's DailyWire account info.

    Proxies the DailyWire middleware API, returning 502 if upstream is unavailable.
    """
    try:
        return get_user_info()
    except Exception as e:
        # Map any unhandled error to a 502 Bad Gateway since we're proxying upstream
        raise HTTPException(status_code=502, detail=str(e))
