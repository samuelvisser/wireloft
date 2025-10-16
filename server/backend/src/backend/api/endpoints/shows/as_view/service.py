from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from fastapi import HTTPException

from backend.api.models.show import ShowAPIRead, ShowAPIReadView
from backend.db.models import Show, Episode

@dataclass(frozen=True)
class ViewFields:
    episode_count: int = ""
    years: str = ""

def _query_view_fields(s: Session, item: Show) -> ViewFields:
    # Compute episode count for this show
    count = (
                s.query(func.count())
                .select_from(Episode)
                .filter(Episode.show_id == item.id)
                .scalar()
            ) or 0

    min_dt, max_dt = (
            s.query(
                func.min(Episode.published_date),
                func.max(Episode.published_date)
            )
            .filter(Episode.show_id == item.id)
            .one_or_none()
            or (None, None)
    )
    years = ""
    if min_dt and max_dt:
        years = f"{min_dt.year}-{max_dt.year}"

    return ViewFields(episode_count=count, years=years)


def _to_view(item: Show, view_fields: ViewFields) -> ShowAPIReadView:
    base = ShowAPIRead.model_validate(item).model_dump()

    return ShowAPIReadView.model_validate({
        **base,
        "episode_count": view_fields.episode_count,
        "years": view_fields.years,
    })


def get_show_views_list(s: Session) -> list[ShowAPIReadView]:
    shows: Sequence[Show] = s.scalars(
        select(Show)
        .order_by(Show.title.asc())
    ).all()

    if shows.__len__() > 0:
        view_fields = _query_view_fields(s, shows[0])
    else:
        view_fields = ViewFields()

    return [_to_view(show, view_fields) for show in shows]

def get_show_view(s: Session, show_slug: str) -> ShowAPIReadView:
    show: Optional[Show] = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    return _to_view(show, _query_view_fields(s, show))
