from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Show, Season, Episode


def get_shows(s: Session, *, show_id: Optional[int], show_slug: Optional[str]) -> Sequence[Show]:
    """Resolve an explicit Show scope, selecting only what we need"""
    if show_slug:
        show = s.scalar(select(Show).where(Show.slug == show_slug))
        return [show] if show is not None else []

    if show_id is not None:
        show = s.get(Show, show_id)
        return [show] if show is not None else []

    return s.scalars(select(Show)).all()


def get_season_from_list_by_id(season_list: list[Season], season_id: int) -> Optional[Season]:
    for season in season_list:
        if season.id == season_id:
            return season
    return None


def get_latest_ep_index(s: Session, *, show: Show) -> Optional[int]:
    return s.execute(select(Episode.index).where(Episode.show_id == show.id).order_by(Episode.index.desc()).limit(1)).scalar()
