from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Show


def get_shows(s: Session, *, resource_id: Optional[int], show_slug: Optional[str]) -> Sequence[Show]:
    # In case we're only interested in one show, get it from the database
    show: Optional[Show] = None
    if show_slug:
        show = s.execute(select(Show).where(Show.slug == show_slug)).scalar_one_or_none()
    elif resource_id is not None:
        show = s.get(Show, resource_id)

    shows: Sequence[Show] = []
    if show is not None:
        shows = [show]
    else:
        shows = s.execute(select(Show)).scalars().all()
    return shows