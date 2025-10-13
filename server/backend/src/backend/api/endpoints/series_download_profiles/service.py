from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.series_download_profile import *
from backend.db.models.download_profile import SeriesDownloadProfile


def get_series_download_profiles_list(s: Session) -> list[SeriesDownloadProfileAPIRead]:
    items = (
        s.query(SeriesDownloadProfile)
        .order_by(SeriesDownloadProfile.id)
        .all()
    )
    return [SeriesDownloadProfileAPIRead.model_validate(it) for it in items]


def get_download_profile_series(s: Session, download_profile_series_id: int) -> SeriesDownloadProfileAPIRead:
    item = (
        s.query(SeriesDownloadProfile)
        .filter_by(id=download_profile_series_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile for series not found")

    return SeriesDownloadProfileAPIRead.model_validate(item)


def create_download_profile_series(s: Session, body: SeriesDownloadProfileAPICreate) -> SeriesDownloadProfileAPIRead:
    data = body.model_dump(by_alias=True)
    item = SeriesDownloadProfile(**data)
    s.add(item)
    s.flush()
    return SeriesDownloadProfileAPIRead.model_validate(item)


def update_download_profile_series(s: Session, download_profile_series_id: int, body: SeriesDownloadProfileAPIUpdate) -> SeriesDownloadProfileAPIRead:
    item = (
        s.query(SeriesDownloadProfile)
        .filter_by(id=download_profile_series_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile for series not found")

    update_database_fields(item, body)
    s.flush()
    return SeriesDownloadProfileAPIRead.model_validate(item)


def delete_download_profile_series(s: Session, download_profile_series_id: int) -> SeriesDownloadProfileAPIRead:
    item = (
        s.query(SeriesDownloadProfile)
        .filter_by(id=download_profile_series_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile for series not found")

    payload = SeriesDownloadProfileAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
