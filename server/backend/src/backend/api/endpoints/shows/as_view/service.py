from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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


def _episode_stats():
    return (
        select(
            Episode.show_id.label("show_id"),
            func.count(Episode.id).label("episode_count"),
            func.min(Episode.published_date).label("min_published_date"),
            func.max(Episode.published_date).label("max_published_date"),
        )
        .group_by(Episode.show_id)
        .subquery()
    )


def _show_view_statement():
    stats = _episode_stats()
    return (
        select(
            Show,
            func.coalesce(stats.c.episode_count, 0),
            stats.c.min_published_date,
            stats.c.max_published_date,
        )
        .outerjoin(stats, stats.c.show_id == Show.id)
    )


def _to_view(
    show: Show,
    episode_count: int,
    min_published_date,
    max_published_date,
) -> ShowAPIReadView:
    years = (
        f"{min_published_date.year}-{max_published_date.year}"
        if min_published_date and max_published_date
        else ""
    )
    return ShowAPIReadView.model_validate(_ShowViewSource(
        show=show,
        episode_count=int(episode_count or 0),
        years=years,
    ))


def get_show_views_list(s: Session) -> list[ShowAPIReadView]:
    rows = s.execute(_show_view_statement().order_by(Show.title.asc())).all()
    return [_to_view(*row) for row in rows]


def get_show_view(s: Session, show_slug: str) -> ShowAPIReadView:
    show: Optional[Show] = s.query(Show).filter_by(slug=show_slug).one_or_none()
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    episode_count, min_published_date, max_published_date = s.execute(
        select(
            func.count(Episode.id),
            func.min(Episode.published_date),
            func.max(Episode.published_date),
        ).where(Episode.show_id == show.id)
    ).one()
    return _to_view(
        show,
        episode_count,
        min_published_date,
        max_published_date,
    )
