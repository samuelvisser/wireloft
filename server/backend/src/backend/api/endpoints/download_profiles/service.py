from __future__ import annotations

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.download_profile import *
from backend.app import db_session
from backend.db.models import DownloadProfile


def get_download_profiles_list() -> list[DownloadProfileAPIRead]:
    with db_session() as s:
        items = (
            s.query(DownloadProfile)
            .order_by(DownloadProfile.id)
            .all()
        )
        return [DownloadProfileAPIRead.model_validate(it, from_attributes=True) for it in items]


def get_download_profile(download_profile_id: int) -> DownloadProfileAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfile)
            .filter_by(id=download_profile_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile not found")

        return DownloadProfileAPIRead.model_validate(item, from_attributes=True)


def create_download_profile(body: DownloadProfileAPICreate) -> DownloadProfileAPIRead:
    with db_session() as s:
        data = body.model_dump(by_alias=True)
        item = DownloadProfile(**data)
        s.add(item)
        s.commit()
        s.refresh(item)
        return DownloadProfileAPIRead.model_validate(item, from_attributes=True)


def update_download_profile(download_profile_id: int, body: DownloadProfileAPIUpdate) -> DownloadProfileAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfile)
            .filter_by(id=download_profile_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile not found")

        update_database_fields(item, body)
        s.commit()
        s.refresh(item)
        return DownloadProfileAPIRead.model_validate(item, from_attributes=True)


def delete_download_profile(download_profile_id: int) -> DownloadProfileAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfile)
            .filter_by(id=download_profile_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile not found")

        payload = DownloadProfileAPIRead.model_validate(item, from_attributes=True)
        s.delete(item)
        s.commit()
        return payload
