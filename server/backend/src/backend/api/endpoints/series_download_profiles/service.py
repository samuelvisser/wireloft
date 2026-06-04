from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.api.helpers import create_database_fields, update_database_fields
from backend.api.models.series_download_profile import *
from backend.db.models.download_profile import SeriesDownloadProfile
from backend.db.models import Season
from task_manager.events.emitters import emit_event


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


def _resolve_or_create_seasons_for_show(s: Session, show_id: int, seasons_req: list[SeasonAPIRequestDetached]) -> list[Season]:
    # If empty list provided, clear association
    if not seasons_req:
        return []

    # Collect slugs from request
    slugs = {se.slug for se in seasons_req if getattr(se, 'slug', None)}

    existing: list[Season] = []
    if slugs:
        existing = (
            s.query(Season)
            .filter(Season.show_id == show_id)
            .filter(Season.slug.in_(slugs))
            .all()
        )

    by_slug = {se.slug: se for se in existing}

    result: list[Season] = []
    seen_ids: set[int] = set()

    for season_in in seasons_req:
        match = by_slug.get(season_in.slug)
        if match is None:
            # Create new Season for this show
            data = season_in.model_dump(exclude_none=True, exclude_unset=True)
            data["show_id"] = show_id
            match = create_database_fields(Season, data)
            s.add(match)
            # Also register into map so next duplicates reuse
            by_slug.setdefault(match.slug, match)
        if match.id is not None:
            if match.id not in seen_ids:
                result.append(match)
                seen_ids.add(match.id)
        else:
            # Not flushed yet, use object identity to avoid duplicates
            if id(match) not in seen_ids:
                result.append(match)
                seen_ids.add(id(match))

    return result


def create_download_profile_series(s: Session, body: SeriesDownloadProfileAPICreate) -> SeriesDownloadProfileAPIRead:
    # Create the profile without directly assigning seasons
    data = body.model_dump(by_alias=True, exclude={"seasons"}, exclude_none=True, exclude_unset=True)
    item = SeriesDownloadProfile(**data)
    s.add(item)

    # Resolve existing seasons or create missing ones for this show
    seasons = _resolve_or_create_seasons_for_show(s, show_id=item.show_id, seasons_req=body.seasons)
    item.seasons = seasons

    s.flush()

    emit_event("download_profile.added", {
        "resource_id": item.id,
        "id": item.id,
        "name": item.name
    })

    return SeriesDownloadProfileAPIRead.model_validate(item)


def update_download_profile_series(s: Session, download_profile_series_id: int, body: SeriesDownloadProfileAPIUpdate) -> SeriesDownloadProfileAPIRead:
    item: Optional[SeriesDownloadProfile] = (
        s.query(SeriesDownloadProfile)
        .filter_by(id=download_profile_series_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile for series not found")

    # Update scalar fields but do not assign seasons directly from body
    update_database_fields(item, body, exclude_fields={"seasons"})

    # Resolve existing seasons or create missing ones for this show
    seasons = _resolve_or_create_seasons_for_show(s, show_id=item.show_id, seasons_req=body.seasons)
    item.seasons = seasons

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

    emit_event("download_profile.deleted", {
        "resource_id": item.id,
        "id": item.id
    })

    s.delete(item)
    s.flush()
    return payload
