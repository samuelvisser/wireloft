from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.download_profile_series import *
from backend.db.models import DownloadProfileSeries


def get_series_download_profiles_list(s: Session) -> list[DownloadProfileSeriesAPIRead]:
    items = (
        s.query(DownloadProfileSeries)
        .order_by(DownloadProfileSeries.id)
        .all()
    )
    return [DownloadProfileSeriesAPIRead.model_validate(it) for it in items]


def get_download_profile_series(s: Session, download_profile_series_id: int) -> DownloadProfileSeriesAPIRead:
    item = (
        s.query(DownloadProfileSeries)
        .filter_by(id=download_profile_series_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile for series not found")

    return DownloadProfileSeriesAPIRead.model_validate(item)


def create_download_profile_series(s: Session, body: DownloadProfileSeriesAPICreate) -> DownloadProfileSeriesAPIRead:
    data = body.model_dump(by_alias=True)
    item = DownloadProfileSeries(**data)
    s.add(item)
    s.flush()
    return DownloadProfileSeriesAPIRead.model_validate(item)


def update_download_profile_series(s: Session, download_profile_series_id: int, body: DownloadProfileSeriesAPIUpdate) -> DownloadProfileSeriesAPIRead:
    item = (
        s.query(DownloadProfileSeries)
        .filter_by(id=download_profile_series_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile for series not found")

    update_database_fields(item, body)
    s.flush()
    return DownloadProfileSeriesAPIRead.model_validate(item)


def delete_download_profile_series(s: Session, download_profile_series_id: int) -> DownloadProfileSeriesAPIRead:
    item = (
        s.query(DownloadProfileSeries)
        .filter_by(id=download_profile_series_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile for series not found")

    payload = DownloadProfileSeriesAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
