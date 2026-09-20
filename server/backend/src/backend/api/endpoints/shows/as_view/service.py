from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.models.show import ShowAPIReadView
from backend.db.models import Episode, Show


@dataclass(frozen=True)
class _ShowViewSource:
    show: Show
    episode_count: int
    years: str


def _view_source(s: Session, show: Show) -> _ShowViewSource:
    count = (
        s.query(func.count())
        .select_from(Episode)
        .filter(Episode.show_id == show.id)
        .scalar()
    ) or 0
    min_dt, max_dt = (
        s.query(func.min(Episode.published_date), func.max(Episode.published_date))
        .filter(Episode.show_id == show.id)
        .one_or_none()
        or (None, None)
    )
    years = f"{min_dt.year}-{max_dt.year}" if min_dt and max_dt else ""
    return _ShowViewSource(show=show, episode_count=count, years=years)


def _to_view(s: Session, show: Show) -> ShowAPIReadView:
    return ShowAPIReadView.model_validate(_view_source(s, show))


def get_show_views_list(s: Session) -> list[ShowAPIReadView]:
    shows: Sequence[Show] = s.scalars(select(Show).order_by(Show.title.asc())).all()
    return [_to_view(s, show) for show in shows]


def get_show_view(s: Session, show_slug: str) -> ShowAPIReadView:
    show: Optional[Show] = s.query(Show).filter_by(slug=show_slug).one_or_none()
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")
    return _to_view(s, show)
