from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.season import *
from backend.db.models import Season


def get_seasons_list(s: Session, show_slug: str) -> list[SeasonAPIRead]:
    seasons = (
        s.query(Season)
        .filter(
            Season.show.has(slug=show_slug)
        )
        .order_by(Season.id)
        .all()
    )
    return [SeasonAPIRead.model_validate(season) for season in seasons]


def get_season(s: Session, show_slug: str, season_slug: str) -> SeasonAPIRead:
    season = (
        s.query(Season)
        .filter(
            Season.slug == season_slug,
            Season.show.has(slug=show_slug)
        )
        .one_or_none()
    )
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")

    return SeasonAPIRead.model_validate(season)


def create_season(s: Session, body: SeasonAPICreate) -> SeasonAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    season = Season(**data)
    s.add(season)
    s.flush()
    return SeasonAPIRead.model_validate(season)


def update_season(s: Session, show_slug: str, season_slug: str, body: SeasonAPIUpdate) -> SeasonAPIRead:
    season = (
        s.query(Season)
        .filter(
            Season.slug == season_slug,
            Season.show.has(slug=show_slug)
        )
        .one_or_none()
    )
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")

    # Apply updates and flush; commit in router
    update_database_fields(season, body)
    s.flush()
    return SeasonAPIRead.model_validate(season)


def delete_season(s: Session, show_slug: str, season_slug: str) -> SeasonAPIRead:
    season = (
        s.query(Season)
        .filter(
            Season.slug == season_slug,
            Season.show.has(slug=show_slug)
        )
        .one_or_none()
    )
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")

    payload = SeasonAPIRead.model_validate(season)
    s.delete(season)
    s.flush()
    return payload