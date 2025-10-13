from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.models.download_profile import DownloadProfileAPIRead
from backend.db.models.download_profile import DownloadProfileBase


def get_download_profiles_list(s: Session) -> list[DownloadProfileAPIRead]:
    items = (
        s.query(DownloadProfileBase)
        .order_by(DownloadProfileBase.id)
        .all()
    )
    return [DownloadProfileAPIRead.model_validate(it) for it in items]


def get_download_profile(s: Session, download_profile_id: int) -> DownloadProfileAPIRead:
    item = (
        s.query(DownloadProfileBase)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    return DownloadProfileAPIRead.model_validate(item)
