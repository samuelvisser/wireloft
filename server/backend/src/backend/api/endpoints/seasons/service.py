from __future__ import annotations

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.season import *
from backend.app import db_session
from backend.db.models import Season


def get_seasons_list() -> list[SeasonAPIRead]:
    with db_session() as s:
        seasons = (
            s.query(Season)
            .order_by(Season.id)
            .all()
        )
        return [SeasonAPIRead.model_validate(season) for season in seasons]


def get_season(season_slug: str) -> SeasonAPIRead:
    with db_session() as s:
        season = (
            s.query(Season)
            .filter_by(slug=season_slug)
            .one_or_none()
        )
        if season is None:
            raise HTTPException(status_code=404, detail="Season not found")

        return SeasonAPIRead.model_validate(season)


def create_season(body: SeasonAPICreate) -> SeasonAPIRead:
    with db_session() as s:
        # Build model from validated Pydantic data
        data = body.model_dump(by_alias=True)

        season = Season(**data)
        s.add(season)
        s.commit()
        s.refresh(season)
        return SeasonAPIRead.model_validate(season)


def update_season(season_slug: str, body: SeasonAPIUpdate) -> SeasonAPIRead:
    with db_session() as s:
        season = (
            s.query(Season)
            .filter_by(slug=season_slug)
            .one_or_none()
        )
        if season is None:
            raise HTTPException(status_code=404, detail="Season not found")

        # Commit and return
        update_database_fields(season, body)
        s.commit()
        s.refresh(season)
        return SeasonAPIRead.model_validate(season)


def delete_season(season_slug: str) -> SeasonAPIRead:
    with db_session() as s:
        season = (
            s.query(Season)
            .filter_by(slug=season_slug)
            .one_or_none()
        )
        if season is None:
            raise HTTPException(status_code=404, detail="Season not found")

        payload = SeasonAPIRead.model_validate(season)
        s.delete(season)
        s.commit()
        return payload