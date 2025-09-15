from __future__ import annotations

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.download_profile_series import *
from backend.app import db_session
from backend.db.models import DownloadProfileSeries


def get_series_download_profiles_list() -> list[DownloadProfileSeriesAPIRead]:
    with db_session() as s:
        items = (
            s.query(DownloadProfileSeries)
            .order_by(DownloadProfileSeries.id)
            .all()
        )
        return [DownloadProfileSeriesAPIRead.model_validate(it) for it in items]


def get_download_profile_series(download_profile_series_id: int) -> DownloadProfileSeriesAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfileSeries)
            .filter_by(id=download_profile_series_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile for series not found")

        return DownloadProfileSeriesAPIRead.model_validate(item)


def create_download_profile_series(body: DownloadProfileSeriesAPICreate) -> DownloadProfileSeriesAPIRead:
    with db_session() as s:
        data = body.model_dump(by_alias=True)
        item = DownloadProfileSeries(**data)
        s.add(item)
        s.commit()
        s.refresh(item)
        return DownloadProfileSeriesAPIRead.model_validate(item)


def update_download_profile_series(download_profile_series_id: int, body: DownloadProfileSeriesAPIUpdate) -> DownloadProfileSeriesAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfileSeries)
            .filter_by(id=download_profile_series_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile for series not found")

        update_database_fields(item, body)
        s.commit()
        s.refresh(item)
        return DownloadProfileSeriesAPIRead.model_validate(item)


def delete_download_profile_series(download_profile_series_id: int) -> DownloadProfileSeriesAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfileSeries)
            .filter_by(id=download_profile_series_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile for series not found")

        payload = DownloadProfileSeriesAPIRead.model_validate(item)
        s.delete(item)
        s.commit()
        return payload
