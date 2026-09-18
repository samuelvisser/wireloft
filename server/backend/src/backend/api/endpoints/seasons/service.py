from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.season import *
from backend.db.models import Season
from backend.types.season_types import SeasonType
from backend.types.show_types import ShowType
from backend.utils.season_ordering import season_type_from_name
from task_manager.events.transactional import queue_event


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


def create_season(s: Session, body: SeasonAPICreate, *, update_show_profiles=False) -> SeasonAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    season_type = season_type_from_name(body.name)
    if season_type is SeasonType.EXTRA:
        season_number = 0
    else:
        season_number = max(
            (
                existing.season_number
                for existing in s.query(Season).filter(Season.show_id == body.show_id)
                if existing.season_type == SeasonType.NORMAL.value
            ),
            default=0,
        ) + 1

    season = Season(
        **data,
        season_type=season_type.value,
        season_number=season_number,
    )
    s.add(season)
    s.flush()

    # Update series download profiles if they include upcoming seasons
    if update_show_profiles and season.show.type == ShowType.SERIES.value:
        for profile in season.show.download_profiles:
            if profile.include_upcoming_seasons:
                profile_seasons: list[Season] = profile.seasons
                profile_seasons.append(season)
                profile.seasons = profile_seasons
                s.flush()

    queue_event(s, "season.added", {
        "resource_id": season.id,
        "id": season.id,
        "slug": season.slug,
        "show_id": season.show_id
    })

    return SeasonAPIRead.model_validate(season)


def update_season(s: Session, show_slug: str, season_slug: str, body: SeasonAPIUpdate) -> SeasonAPIRead:
    season: Optional[Season] = (
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

    queue_event(s, "season.deleted", {
        "resource_id": season.id,
        "id": season.id,
        "slug": season.slug,
        "show_id": season.show_id
    })

    s.delete(season)
    s.flush()
    return payload
